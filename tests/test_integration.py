"""End-to-end tests for synthetic Aperio compression-33007 TIFF input."""

import struct
from pathlib import Path

import numpy as np
import pytest
import tifffile

from svs_to_ometiff import ConvertConfig, convert
import svs_to_ometiff.converter as converter_module


def _make_known_yuyv_tile(width: int, height: int) -> bytes:
    """Return neutral-chroma YUYV bytes whose RGB output equals luma."""
    if width % 2:
        raise ValueError("width must be even")

    raw = bytearray()
    for y in range(height):
        for x in range(0, width, 2):
            y0 = (y * width + x) % 256
            y1 = (y * width + x + 1) % 256
            raw.extend([y0, 128, y1, 128])
    return bytes(raw)


def _write_synthetic_33007_svs(path: Path, width: int = 16, height: int = 16) -> None:
    """
    Write a tiled TIFF whose tile payload is raw YUYV, then patch compression.

    tifffile does not encode Aperio 33007. The production reader bypasses
    tifffile image decoding and reads tile byte ranges directly, so this
    fixture creates a valid tiled TIFF container with the exact raw tile bytes
    the decoder expects.
    """
    raw = _make_known_yuyv_tile(width, height)
    data = np.frombuffer(raw, dtype="<u2").reshape(height, width)

    with tifffile.TiffWriter(path) as tif:
        tif.write(
            data,
            tile=(16, 16),
            photometric="minisblack",
            metadata=None,
            description="Aperio synthetic|MPP = 0.5",
        )

    with tifffile.TiffFile(path) as tif:
        compression_value_offset = tif.pages[0].tags["Compression"].valueoffset

    with path.open("r+b") as handle:
        handle.seek(compression_value_offset)
        handle.write(struct.pack("<H", 33007))


def test_full_pipeline_synthetic_33007(tmp_path: Path) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    _write_synthetic_33007_svs(input_svs)

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

    expected_luma = np.arange(16 * 16, dtype=np.uint8).reshape(16, 16)
    expected_rgb = np.repeat(expected_luma[:, :, np.newaxis], 3, axis=2)
    np.testing.assert_array_equal(level0, expected_rgb)

    expected_level1 = (
        expected_rgb.reshape(8, 2, 8, 2, 3).mean(axis=(1, 3)).astype(np.uint8)
    )
    np.testing.assert_array_equal(level1, expected_level1)


def test_convert_keeps_legacy_arguments_working(tmp_path: Path) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    _write_synthetic_33007_svs(input_svs)

    result = convert(
        str(input_svs),
        str(output_ometiff),
        tile_size=16,
        compression=None,
        num_levels=1,
        verbose=False,
    )

    assert result["pyramid_shapes"] == [(16, 16, 3)]


def test_convert_explains_missing_imagecodecs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output_ometiff = tmp_path / "synthetic.ome.tiff"
    _write_synthetic_33007_svs(input_svs)

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
    _write_synthetic_33007_svs(input_svs)

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
