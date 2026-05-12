"""Shared test helpers for synthetic Aperio compression-33007 fixtures."""

import struct
from pathlib import Path

import numpy as np
import tifffile


def make_known_yuyv_tile(width: int, height: int) -> bytes:
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


def expected_rgb_from_luma(width: int, height: int) -> np.ndarray:
    """Expected RGB image for make_known_yuyv_tile's neutral chroma pattern."""
    expected_luma = np.arange(width * height, dtype=np.uint8).reshape(height, width)
    return np.repeat(expected_luma[:, :, np.newaxis], 3, axis=2)


def write_synthetic_33007_svs(path: Path, width: int = 16, height: int = 16) -> None:
    """
    Write a tiled TIFF whose tile payload is raw YUYV, then patch compression.

    tifffile does not encode Aperio 33007. The production reader bypasses
    tifffile image decoding and reads tile byte ranges directly, so this
    fixture creates a valid tiled TIFF container with the exact raw tile bytes
    the decoder expects.
    """
    raw = make_known_yuyv_tile(width, height)
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
