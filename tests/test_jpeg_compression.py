"""Tests for JPEG and JPEG 2000 compression support (v0.7.0)."""

import numpy as np
import pytest

from svs_to_ometiff.config import _SUPPORTED_COMPRESSION, ConvertConfig
from svs_to_ometiff.converter import _check_codec
from svs_to_ometiff.writer import write_pyramidal_ometiff_from_levels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_codec(compression: str) -> bool:
    """Return True if the required imagecodecs codec is installed.

    Uses module-level constants as capability indicators (``JPEG`` / ``JPEG2K``
    are only present when the corresponding codec was built).  Does NOT call
    encode functions to avoid segfaults on invalid probe data.
    """
    try:
        import imagecodecs
    except ImportError:
        return False
    if compression == "jpeg":
        return hasattr(imagecodecs, "JPEG")
    return hasattr(imagecodecs, "JPEG2K")


def _make_rgb_level(width: int, height: int) -> np.ndarray:
    """Create a minimal uint8 RGB image."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# _SUPPORTED_COMPRESSION
# ---------------------------------------------------------------------------

class TestSupportedCompression:
    """The supported compression tuple includes jpeg and jpeg2000."""

    def test_includes_legacy_options(self):
        assert None in _SUPPORTED_COMPRESSION
        assert "lzw" in _SUPPORTED_COMPRESSION
        assert "zlib" in _SUPPORTED_COMPRESSION
        assert "deflate" in _SUPPORTED_COMPRESSION

    def test_includes_jpeg(self):
        assert "jpeg" in _SUPPORTED_COMPRESSION

    def test_includes_jpeg2000(self):
        assert "jpeg2000" in _SUPPORTED_COMPRESSION

    def test_is_tuple(self):
        assert isinstance(_SUPPORTED_COMPRESSION, tuple)


# ---------------------------------------------------------------------------
# ConvertConfig — compression acceptance
# ---------------------------------------------------------------------------

class TestConvertConfigCompression:
    """ConvertConfig accepts jpeg and jpeg2000 as valid compression values."""

    def test_accepts_jpeg(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compression="jpeg",
        )
        assert config.compression == "jpeg"

    def test_accepts_jpeg2000(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compression="jpeg2000",
        )
        assert config.compression == "jpeg2000"

    def test_none_normalization(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compression="none",
        )
        assert config.compression is None


# ---------------------------------------------------------------------------
# ConvertConfig — compressionargs field
# ---------------------------------------------------------------------------

class TestConvertConfigCompressionArgs:
    """ConvertConfig compressionargs field and serialization."""

    def test_default_is_none(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
        )
        assert config.compressionargs is None

    def test_set_dict(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compressionargs={"level": 80, "subsampling": "4:2:0"},
        )
        assert config.compressionargs == {"level": 80, "subsampling": "4:2:0"}

    def test_to_dict_includes_compressionargs(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compressionargs={"level": 90},
        )
        d = config.to_dict()
        assert d["compressionargs"] == {"level": 90}

    def test_to_dict_omits_compressionargs_when_none(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
        )
        d = config.to_dict()
        assert d["compressionargs"] is None

    def test_from_dict_accepts_dict(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "compressionargs": {"level": 75},
        })
        assert config.compressionargs == {"level": 75}

    def test_from_dict_parses_json_string(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "compressionargs": '{"level": 50}',
        })
        assert config.compressionargs == {"level": 50}

    def test_from_dict_ignores_invalid_json_string(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "compressionargs": "not-json",
        })
        assert config.compressionargs == "not-json"

    def test_round_trip_with_compressionargs(self):
        config = ConvertConfig(
            input_svs="/a.svs",
            output_ometiff="/b.ome.tiff",
            compression="jpeg",
            compressionargs={"level": 85},
        )
        restored = ConvertConfig.from_dict(config.to_dict())
        assert restored.compression == "jpeg"
        assert restored.compressionargs == {"level": 85}


# ---------------------------------------------------------------------------
# Codec detection
# ---------------------------------------------------------------------------

class TestCodecDetection:
    """_check_codec raises RuntimeError when required codec is missing."""

    def test_no_op_for_none_compression(self):
        _check_codec(None)

    def test_no_op_for_zlib(self):
        _check_codec("zlib")

    def test_no_op_for_lzw(self):
        _check_codec("lzw")

    def test_no_op_for_deflate(self):
        _check_codec("deflate")

    def test_raises_for_jpeg_when_imagecodecs_missing(self, monkeypatch):
        monkeypatch.setitem(
            __import__("sys").modules, "imagecodecs", None
        )

        with pytest.raises(RuntimeError, match="requires imagecodecs"):
            _check_codec("jpeg")

    def test_raises_for_jpeg2000_when_imagecodecs_missing(self, monkeypatch):
        monkeypatch.setitem(
            __import__("sys").modules, "imagecodecs", None
        )

        with pytest.raises(RuntimeError, match="requires imagecodecs"):
            _check_codec("jpeg2000")

    def test_raises_for_jpeg_when_codec_missing(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "imagecodecs", None)

        with pytest.raises(RuntimeError, match="requires imagecodecs"):
            _check_codec("jpeg")

    def test_raises_for_jpeg2000_when_codec_missing(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "imagecodecs", None)

        with pytest.raises(RuntimeError, match="requires imagecodecs"):
            _check_codec("jpeg2000")


# ---------------------------------------------------------------------------
# JPEG / JPEG 2000 writer integration
# ---------------------------------------------------------------------------

@pytest.fixture()
def rgb_level():
    """Return a single (16, 16, 3) uint8 RGB level for minimal writes."""
    return [_make_rgb_level(16, 16)]


@pytest.mark.skipif(not _has_codec("jpeg"), reason="imagecodecs[jpeg] codec not installed")
class TestJPEGWriter:
    """End-to-end JPEG compression write tests."""

    def test_write_jpeg_compressed_ometiff(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg_test.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg",
            compressionargs={"level": 80},
            verbose=False,
        )
        assert output.exists()
        assert output.stat().st_size > 0

    def test_write_jpeg_without_compressionargs(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg_noargs.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg",
            verbose=False,
        )
        assert output.exists()

    def test_write_jpeg_multi_level(self, tmp_path):
        rng = np.random.default_rng(42)
        level0 = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
        level1 = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
        output = tmp_path / "jpeg_multi.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            [level0, level1],
            mpp=0.5,
            tile_size=16,
            compression="jpeg",
            compressionargs={"level": 90},
            verbose=False,
        )
        assert output.exists()

    def test_jpeg_is_lossy(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg_lossy.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg",
            compressionargs={"level": 1},
            verbose=False,
        )
        output2 = tmp_path / "jpeg_highq.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output2),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg",
            compressionargs={"level": 100},
            verbose=False,
        )
        assert output.stat().st_size != output2.stat().st_size


@pytest.mark.skipif(not _has_codec("jpeg2000"), reason="imagecodecs[jpeg2k] codec not installed")
class TestJPEG2000Writer:
    """End-to-end JPEG 2000 compression write tests."""

    def test_write_jpeg2000_compressed_ometiff(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg2k_test.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg2000",
            verbose=False,
        )
        assert output.exists()
        assert output.stat().st_size > 0

    def test_write_jpeg2000_with_compressionargs(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg2k_args.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg2000",
            compressionargs={"codecformat": 0},
            verbose=False,
        )
        assert output.exists()

    def test_write_jpeg2000_multi_level(self, tmp_path):
        rng = np.random.default_rng(42)
        level0 = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
        level1 = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
        output = tmp_path / "jpeg2k_multi.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            [level0, level1],
            mpp=0.5,
            tile_size=16,
            compression="jpeg2000",
            verbose=False,
        )
        assert output.exists()

    def test_jpeg2000_lossless_roundtrip(self, tmp_path, rgb_level):
        output = tmp_path / "jpeg2k_roundtrip.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="jpeg2000",
            verbose=False,
        )
        import tifffile
        with tifffile.TiffFile(str(output)) as tif:
            decoded = tif.asarray()
        np.testing.assert_array_equal(decoded, rgb_level[0])


@pytest.mark.skipif(not _has_codec("jpeg"), reason="imagecodecs[jpeg] codec not installed")
class TestCompressionArgsPassthrough:
    """compressionargs flows through writer to tifffile."""

    def test_null_compressionargs_no_error(self, tmp_path, rgb_level):
        output = tmp_path / "null_args.ome.tiff"
        write_pyramidal_ometiff_from_levels(
            str(output),
            rgb_level,
            mpp=0.5,
            tile_size=16,
            compression="zlib",
            compressionargs=None,
            verbose=False,
        )
        assert output.exists()


# ---------------------------------------------------------------------------
# CLI --compression-args acceptance (via _parse_json_dict)
# ---------------------------------------------------------------------------

class TestCLICompressionArgsParsing:
    """--compression-args JSON parsing via _parse_json_dict callback."""

    def test_parse_json_dict_valid(self):
        from svs_to_ometiff.cli import _parse_json_dict

        result = _parse_json_dict(None, None, '{"level": 85}')
        assert result == {"level": 85}

    def test_parse_json_dict_none(self):
        from svs_to_ometiff.cli import _parse_json_dict

        result = _parse_json_dict(None, None, None)
        assert result is None

    def test_parse_json_dict_invalid_json(self):
        from svs_to_ometiff.cli import _parse_json_dict
        import click

        with pytest.raises(click.BadParameter, match="invalid JSON"):
            _parse_json_dict(None, None, "{bad")

    def test_parse_json_dict_not_a_dict(self):
        from svs_to_ometiff.cli import _parse_json_dict
        import click

        with pytest.raises(click.BadParameter, match="must be a JSON object"):
            _parse_json_dict(None, None, "42")
