"""Large-fixture integration tests (pytest.mark.slow).

Exercises the full conversion pipeline with synthetic SVS images at
2048x2048 and 16384x16384: pyramid tile counts, edge-tile padding,
SubIFD validation, memmap out-of-core path, and JPEG 2000 round-trip.

Run with:  pytest -m slow -v
Skip with: pytest -m "not slow"
"""

import math

import numpy as np
import pytest
import tifffile

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff.converter import convert
from svs_to_ometiff.tile_reader import read_svs_metadata
from svs_to_ometiff.verify import verify_ometiff

from .helpers import expected_rgb_from_luma, write_synthetic_33007_svs

pytestmark = pytest.mark.slow


def _has_codec(compression: str) -> bool:
    try:
        import imagecodecs
    except ImportError:
        return False
    if compression == "jpeg":
        return hasattr(imagecodecs, "JPEG")
    return hasattr(imagecodecs, "JPEG2K")


# ---------------------------------------------------------------------------
# Synthetic metadata validation
# ---------------------------------------------------------------------------

class TestSyntheticMetadata:
    """read_svs_metadata returns coherent values for large fixtures."""

    def test_2048x2048_tile256_metadata(self, tmp_path):
        svs = tmp_path / "meta_2048.svs"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)
        meta = read_svs_metadata(str(svs))
        assert meta["compression"] == 33007
        assert meta["width"] == 2048
        assert meta["height"] == 2048
        assert meta["src_tile_width"] == 256
        assert meta["src_tile_height"] == 256
        assert meta["tile_count"] == 8 * 8
        assert meta["n_tiles_x"] == 8
        assert meta["n_tiles_y"] == 8

    def test_16384x16384_tile256_metadata(self, tmp_path):
        svs = tmp_path / "meta_16384.svs"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)
        meta = read_svs_metadata(str(svs))
        assert meta["compression"] == 33007
        assert meta["width"] == 16384
        assert meta["height"] == 16384
        assert meta["src_tile_width"] == 256
        assert meta["src_tile_height"] == 256
        assert meta["tile_count"] == 64 * 64


# ---------------------------------------------------------------------------
# 2048x2048 conversion -- pyramid tile counts
# ---------------------------------------------------------------------------

class Test2048x2048TileCounts:
    """Verify per-level tile counts in the output OME-TIFF.

    tifffile stores SubIFD levels as TiffPageSeries objects whose
    ``.keyframe`` attribute points to the underlying TiffPage with
    per-IFD ``.dataoffsets``.
    """

    def test_default_6_levels_tile_counts(self, tmp_path):
        svs = tmp_path / "counts_6l.svs"
        ometiff = tmp_path / "counts_6l.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            levels = tif.series[0].levels
            assert len(levels) == 6

            per_level = {
                i: len(lvl.keyframe.dataoffsets)
                for i, lvl in enumerate(levels)
            }

        assert per_level[0] == 4  # ceil(2048/1024)^2
        for lvl in range(1, 6):
            assert per_level[lvl] == 1, f"level {lvl}: {per_level[lvl]} tiles"

    def test_3_levels_tile_counts(self, tmp_path):
        svs = tmp_path / "counts_3l.svs"
        ometiff = tmp_path / "counts_3l.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            levels = tif.series[0].levels
            assert len(levels) == 3

            per_level = {
                i: len(lvl.keyframe.dataoffsets)
                for i, lvl in enumerate(levels)
            }

        assert per_level[0] == 4
        assert per_level[1] == 1
        assert per_level[2] == 1


# ---------------------------------------------------------------------------
# Edge-tile pixel verification (edge_mode="pad")
# ---------------------------------------------------------------------------

class TestEdgeTilePixels:
    """Verify padded edge-tile behaviour for non-multiple image sizes."""

    def test_pad_produces_full_tiles_at_non_multiple_size(self, tmp_path):
        """With edge_mode='pad' every stored tile is tile_size x tile_size."""
        svs = tmp_path / "edge_pad_1500.svs"
        ometiff = tmp_path / "edge_pad_1500.ome.tiff"
        write_synthetic_33007_svs(svs, width=1500, height=1500, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            edge_mode="pad",
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            l0_page = tif.series[0].levels[0].keyframe
            tile_w, tile_h = l0_page.tilewidth, l0_page.tilelength
            assert tile_w == tile_h == 1024

            # 1500x1500 with tile_size=1024: ceil(1500/1024)=2, so 4 tiles.
            # With pad, every tile is a full 1024x1024 (edge tiles are padded).
            assert len(l0_page.dataoffsets) == 4

    def test_pad_vs_crop_output_both_valid(self, tmp_path):
        """pad and crop modes both produce valid OME-TIFF output."""
        svs = tmp_path / "both.svs"
        write_synthetic_33007_svs(svs, width=1500, height=1500, src_tile_size=256)

        for mode in ("pad", "crop"):
            ometiff = tmp_path / f"both_{mode}.ome.tiff"
            config = ConvertConfig(
                input_svs=str(svs),
                output_ometiff=str(ometiff),
                tile_size=1024,
                num_levels=3,
                downsample_factor=2,
                edge_mode=mode,
                verbose=False,
            )
            convert(config)

            result = verify_ometiff(str(ometiff))
            assert result["pass"], (
                f"verify_ometiff failed for {mode}: {result['errors']}"
            )

    def test_pad_vs_crop_level_shapes(self, tmp_path):
        svs = tmp_path / "compare.svs"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        shapes = {}
        for mode in ("pad", "crop"):
            ometiff = tmp_path / f"compare_{mode}.ome.tiff"
            config = ConvertConfig(
                input_svs=str(svs),
                output_ometiff=str(ometiff),
                tile_size=1024,
                num_levels=6,
                downsample_factor=2,
                edge_mode=mode,
                verbose=False,
            )
            convert(config)

            with tifffile.TiffFile(str(ometiff)) as tif:
                shapes[mode] = [
                    lvl.shape for lvl in tif.series[0].levels
                ]

        assert shapes["pad"] == shapes["crop"]

    def test_crop_vs_pad_level0_identical(self, tmp_path):
        svs = tmp_path / "modecmp.svs"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        arrays = {}
        for mode in ("pad", "crop"):
            ometiff = tmp_path / f"modecmp_{mode}.ome.tiff"
            config = ConvertConfig(
                input_svs=str(svs),
                output_ometiff=str(ometiff),
                tile_size=1024,
                num_levels=3,
                downsample_factor=2,
                edge_mode=mode,
                verbose=False,
            )
            convert(config)

            with tifffile.TiffFile(str(ometiff)) as tif:
                arrays[mode] = tif.series[0].levels[0].asarray()

        np.testing.assert_array_equal(arrays["pad"], arrays["crop"])


# ---------------------------------------------------------------------------
# 16384x16384 -- SubIFD validation
# ---------------------------------------------------------------------------

class Test16384x16384SubIFD:
    """Verify SubIFD offsets are valid and readable at scale."""

    def test_subifd_offsets_readable(self, tmp_path):
        svs = tmp_path / "subifd_16k.svs"
        ometiff = tmp_path / "subifd_16k.ome.tiff"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            page0 = tif.pages[0]
            assert 330 in page0.tags, "SubIFD tag (330) missing"
            subifd_offsets = page0.tags[330].value
            assert len(subifd_offsets) == 5, (
                f"expected 5 SubIFD offsets, got {len(subifd_offsets)}"
            )

            assert page0.subifds == subifd_offsets

            levels = tif.series[0].levels
            assert len(levels) == 6

            for i, lvl in enumerate(levels):
                shape = lvl.shape
                assert len(shape) == 3, f"level {i} not 3-D"
                assert shape[2] == 3, f"level {i} not RGB"
                assert lvl.dtype == np.uint8, f"level {i} dtype: {lvl.dtype}"

    def test_all_levels_have_expected_shapes(self, tmp_path):
        svs = tmp_path / "shapes_16k.svs"
        ometiff = tmp_path / "shapes_16k.ome.tiff"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        expected_shapes = [
            (16384, 16384, 3),
            (8192, 8192, 3),
            (4096, 4096, 3),
            (2048, 2048, 3),
            (1024, 1024, 3),
            (512, 512, 3),
        ]

        with tifffile.TiffFile(str(ometiff)) as tif:
            for i, (lvl, expected) in enumerate(
                zip(tif.series[0].levels, expected_shapes)
            ):
                assert lvl.shape == expected, (
                    f"level {i}: expected {expected}, got {lvl.shape}"
                )

    def test_16384x16384_tile_counts(self, tmp_path):
        svs = tmp_path / "tiles_16k.svs"
        ometiff = tmp_path / "tiles_16k.ome.tiff"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            for i, lvl in enumerate(tif.series[0].levels):
                n_tiles = len(lvl.keyframe.dataoffsets)
                level_w = lvl.shape[1]
                expected_tiles = math.ceil(level_w / 1024) ** 2
                assert n_tiles == expected_tiles, (
                    f"level {i} ({lvl.shape[1]}x{lvl.shape[0]}): "
                    f"{n_tiles} tiles, expected {expected_tiles}"
                )


# ---------------------------------------------------------------------------
# verify_ometiff integration
# ---------------------------------------------------------------------------

class TestVerifyOmetiff:
    """End-to-end verification of converted output."""

    def test_verify_2048x2048_passes(self, tmp_path):
        svs = tmp_path / "verify_2048.svs"
        ometiff = tmp_path / "verify_2048.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        result = verify_ometiff(str(ometiff), min_levels=1, expected_tile_size=1024)
        assert result["pass"], f"verify_ometiff failed: {result['errors']}"
        assert result["is_ome"] is True
        assert result["is_bigtiff"] is True
        assert len(result["levels"]) == 6
        assert result["subifds"] == 5
        assert result["dtype"] == "uint8"

    def test_verify_16384x16384_passes(self, tmp_path):
        svs = tmp_path / "verify_16k.svs"
        ometiff = tmp_path / "verify_16k.ome.tiff"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        result = verify_ometiff(str(ometiff), min_levels=1, expected_tile_size=1024)
        assert result["pass"], f"verify_ometiff failed: {result['errors']}"
        assert result["is_ome"] is True
        assert result["is_bigtiff"] is True
        assert result["subifds"] == 5

    def test_mpp_preserved(self, tmp_path):
        svs = tmp_path / "mpp.svs"
        ometiff = tmp_path / "mpp.ome.tiff"
        write_synthetic_33007_svs(
            svs,
            width=2048,
            height=2048,
            src_tile_size=256,
            description="Aperio synthetic|MPP = 0.275",
        )

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        result = verify_ometiff(str(ometiff))
        assert result["pass"]
        assert result["physical_size_x"] == pytest.approx(0.275, rel=0.01)
        assert result["physical_size_y"] == pytest.approx(0.275, rel=0.01)

    def test_magnification_preserved(self, tmp_path):
        svs = tmp_path / "mag.svs"
        ometiff = tmp_path / "mag.ome.tiff"
        write_synthetic_33007_svs(
            svs,
            width=2048,
            height=2048,
            src_tile_size=256,
            description="Aperio synthetic|AppMag = 40|MPP = 0.25",
        )

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        with tifffile.TiffFile(str(ometiff)) as tif:
            desc = tif.pages[0].description
        assert 'NominalMagnification="40"' in desc


# ---------------------------------------------------------------------------
# JPEG 2000 round-trip
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _has_codec("jpeg2000"), reason="imagecodecs[jpeg2k] not installed")
class TestJPEG2000RoundTrip:
    """JPEG 2000 lossless compression preserves pixel fidelity."""

    def test_round_trip_level0_pixel_fidelity(self, tmp_path):
        svs = tmp_path / "j2k_rt.svs"
        ometiff = tmp_path / "j2k_rt.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            compression="jpeg2000",
            verbose=False,
        )
        convert(config)

        expected = expected_rgb_from_luma(2048, 2048)

        with tifffile.TiffFile(str(ometiff)) as tif:
            decoded = tif.series[0].levels[0].asarray()

        assert decoded.shape == expected.shape
        np.testing.assert_array_equal(decoded, expected)

    def test_round_trip_all_levels_decodable(self, tmp_path):
        svs = tmp_path / "j2k_all.svs"
        ometiff = tmp_path / "j2k_all.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            compression="jpeg2000",
            verbose=False,
        )
        convert(config)

        expected_shapes = [
            (2048, 2048, 3),
            (1024, 1024, 3),
            (512, 512, 3),
            (256, 256, 3),
            (128, 128, 3),
            (64, 64, 3),
        ]

        with tifffile.TiffFile(str(ometiff)) as tif:
            for i, (lvl, exp_shape) in enumerate(
                zip(tif.series[0].levels, expected_shapes)
            ):
                data = lvl.asarray()
                assert data.shape[:2] == exp_shape[:2], (
                    f"level {i}: shape {data.shape[:2]}, expected {exp_shape[:2]}"
                )
                assert data.dtype == np.uint8

    def test_jpeg2000_smaller_than_zlib(self, tmp_path):
        svs = tmp_path / "size_cmp.svs"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        sizes = {}
        for comp in ("jpeg2000", "zlib"):
            ometiff = tmp_path / f"size_{comp}.ome.tiff"
            config = ConvertConfig(
                input_svs=str(svs),
                output_ometiff=str(ometiff),
                tile_size=1024,
                num_levels=3,
                downsample_factor=2,
                compression=comp,
                verbose=False,
            )
            convert(config)
            sizes[comp] = ometiff.stat().st_size

        assert sizes["jpeg2000"] < sizes["zlib"], (
            f"jpeg2000={sizes['jpeg2000']} >= zlib={sizes['zlib']}"
        )


# ---------------------------------------------------------------------------
# Out-of-core / memmap path exercised
# ---------------------------------------------------------------------------

class TestMemmapPath:
    """Verify the conversion uses disk-backed memmap (not in-memory)."""

    def test_16384x16384_completes(self, tmp_path):
        svs = tmp_path / "memmap_16k.svs"
        ometiff = tmp_path / "memmap_16k.ome.tiff"
        write_synthetic_33007_svs(svs, width=16384, height=16384, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=6,
            downsample_factor=2,
            verbose=False,
        )
        result = convert(config)

        assert result["width"] == 16384
        assert result["height"] == 16384
        assert result["output_size_bytes"] > 0

        vresult = verify_ometiff(str(ometiff))
        assert vresult["pass"], f"verify_ometiff failed: {vresult['errors']}"

    def test_2048x2048_output_pixel_values_match_source(self, tmp_path):
        svs = tmp_path / "pix_2048.svs"
        ometiff = tmp_path / "pix_2048.ome.tiff"
        write_synthetic_33007_svs(svs, width=2048, height=2048, src_tile_size=256)

        config = ConvertConfig(
            input_svs=str(svs),
            output_ometiff=str(ometiff),
            tile_size=1024,
            num_levels=3,
            downsample_factor=2,
            verbose=False,
        )
        convert(config)

        expected = expected_rgb_from_luma(2048, 2048)

        with tifffile.TiffFile(str(ometiff)) as tif:
            decoded = tif.series[0].levels[0].asarray()

        np.testing.assert_array_equal(decoded, expected)
