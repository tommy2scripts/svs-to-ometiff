"""End-to-end tests for synthetic Aperio compression-33007 TIFF input."""

from pathlib import Path

import numpy as np
import pytest
import tifffile

from svs_to_ometiff import ConvertConfig, convert
import svs_to_ometiff.converter as converter_module
from helpers import expected_rgb_from_luma, write_synthetic_33007_svs


def test_full_pipeline_synthetic_33007(tmp_path: Path) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(input_svs)

    with tifffile.TiffFile(input_svs) as tif:
        assert int(tif.pages[0].tags["Compression"].value) == 33007

    result = convert(
        ConvertConfig(
            input_svs=str(input_svs),
            output_ometiff=str(output_ometiff),
            tile_size=16,
            compression=None,
            num_levels=2,
            verbose=False,
        )
    )

    assert result["pyramid_shapes"] == [(16, 16, 3), (8, 8, 3)]

    with tifffile.TiffFile(output_ometiff) as tif:
        assert tif.is_ome
        assert tif.is_bigtiff
        assert len(tif.series[0].levels) == 2
        assert tif.series[0].levels[0].shape == (16, 16, 3)
        assert tif.series[0].levels[1].shape == (8, 8, 3)

        level0 = tif.series[0].levels[0].asarray()
        level1 = tif.series[0].levels[1].asarray()

    expected_rgb = expected_rgb_from_luma(16, 16)
    np.testing.assert_array_equal(level0, expected_rgb)

    expected_level1 = (
        expected_rgb.reshape(8, 2, 8, 2, 3).mean(axis=(1, 3)).astype(np.uint8)
    )
    np.testing.assert_array_equal(level1, expected_level1)


def test_convert_keeps_legacy_arguments_working(tmp_path: Path) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(input_svs)

    result = convert(
        str(input_svs),
        str(output_ometiff),
        tile_size=16,
        compression=None,
        num_levels=1,
        verbose=False,
    )

    assert result["pyramid_shapes"] == [(16, 16, 3)]

    with tifffile.TiffFile(output_ometiff) as tif:
        assert tif.is_ome
        assert len(tif.series[0].levels) == 1
        assert tif.series[0].levels[0].shape == (16, 16, 3)


def test_convert_explains_missing_imagecodecs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(input_svs)

    def fail_write(*args, **kwargs) -> None:
        raise KeyError("requires the imagecodecs package")

    monkeypatch.setattr(converter_module, "write_pyramidal_ometiff", fail_write)

    with pytest.raises(RuntimeError, match="pip install imagecodecs"):
        convert(
            ConvertConfig(
                input_svs=str(input_svs),
                output_ometiff=str(output_ometiff),
                tile_size=16,
                compression="lzw",
                num_levels=1,
                verbose=False,
            )
        )


def test_convert_suggests_uncompressed_fallback_for_compression_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(input_svs)

    def fail_write(*args, **kwargs) -> None:
        raise RuntimeError("compression encoder failed")

    monkeypatch.setattr(converter_module, "write_pyramidal_ometiff", fail_write)

    with pytest.raises(RuntimeError, match="--compression none"):
        convert(
            ConvertConfig(
                input_svs=str(input_svs),
                output_ometiff=str(output_ometiff),
                tile_size=16,
                compression="lzw",
                num_levels=1,
                verbose=False,
            )
        )
