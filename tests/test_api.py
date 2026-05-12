"""
Tests for the public conversion API shape.

Verifies that ``convert()`` accepts the documented call patterns
and rejects misuse with clear error messages.
"""

import struct
from pathlib import Path

import pytest
import tifffile

from svs_to_ometiff import ConvertConfig, convert
from helpers import write_synthetic_33007_svs


def test_convert_accepts_convertconfig(tmp_path: Path) -> None:
    """convert() with ConvertConfig is the primary API."""
    input_svs = tmp_path / "synthetic.svs"
    output = tmp_path / "out.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    result = convert(
        ConvertConfig(
            input_svs=str(input_svs),
            output_ometiff=str(output),
            tile_size=16,
            compression=None,
            num_levels=1,
            verbose=False,
        )
    )
    assert result["pyramid_shapes"] == [(16, 16, 3)]


def test_convert_accepts_legacy_positional_args(tmp_path: Path) -> None:
    """convert() accepts (input_svs, output_ometiff, **kwargs) for backward compat."""
    input_svs = tmp_path / "synthetic.svs"
    output = tmp_path / "out.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    result = convert(
        str(input_svs),
        str(output),
        tile_size=16,
        compression=None,
        num_levels=1,
        verbose=False,
    )
    assert result["pyramid_shapes"] == [(16, 16, 3)]


def test_convert_rejects_keyword_input_svs(tmp_path: Path) -> None:
    """convert() does not accept input_svs= as a keyword argument
    (the parameter is named config_or_input_svs)."""
    input_svs = tmp_path / "synthetic.svs"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    with pytest.raises(TypeError, match="missing 1 required positional argument"):
        convert(
            input_svs=str(input_svs),
            output_ometiff=str(tmp_path / "out.ome.tiff"),
            tile_size=16,
            compression=None,
            verbose=False,
        )


def test_convert_rejects_missing_output(tmp_path: Path) -> None:
    """Legacy-style convert(input_svs) without output_ometiff raises TypeError."""
    input_svs = tmp_path / "synthetic.svs"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    with pytest.raises(TypeError, match="missing required"):
        convert(str(input_svs))  # type: ignore[call-overload]


def test_convert_rejects_mixing_convertconfig_and_kwargs(tmp_path: Path) -> None:
    """Passing a ConvertConfig plus extra kwargs raises TypeError."""
    input_svs = tmp_path / "synthetic.svs"
    output = tmp_path / "out.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    with pytest.raises(TypeError, match="not both"):
        convert(
            ConvertConfig(
                input_svs=str(input_svs),
                output_ometiff=str(output),
                tile_size=16,
                compression=None,
                num_levels=1,
                verbose=False,
            ),
            str(output),
        )


def test_convert_rejects_unknown_kwargs(tmp_path: Path) -> None:
    """Unknown keyword arguments produce a clear TypeError listing them."""
    input_svs = tmp_path / "synthetic.svs"
    output = tmp_path / "out.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=16, height=16)

    with pytest.raises(TypeError, match="bogus_param"):
        convert(
            str(input_svs),
            str(output),
            bogus_param=42,
        )


def test_convert_rejects_non_33007_compression(tmp_path: Path) -> None:
    """SVS files without compression 33007 are rejected with a clear message."""
    input_path = tmp_path / "not33007.svs"
    output = tmp_path / "out.ome.tiff"

    # Write a tiled TIFF then overwrite the compression tag
    write_synthetic_33007_svs(input_path, width=16, height=16)

    with tifffile.TiffFile(input_path) as tif:
        compression_value_offset = tif.pages[0].tags["Compression"].valueoffset

    with input_path.open("r+b") as handle:
        handle.seek(compression_value_offset)
        handle.write(struct.pack("<H", 7))  # JPEG compression

    with pytest.raises(ValueError, match="only supports Aperio compression 33007"):
        convert(
            ConvertConfig(
                input_svs=str(input_path),
                output_ometiff=str(output),
                verbose=False,
            )
        )
