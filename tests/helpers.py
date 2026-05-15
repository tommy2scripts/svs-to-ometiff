"""Shared test helpers for synthetic Aperio compression-33007 fixtures."""

import struct
from pathlib import Path
from typing import Optional

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


def _make_synthetic_yuyv_data(width: int, height: int) -> np.ndarray:
    """Return uint16 (height, width) array with known YUYV pattern.

    Uses vectorised NumPy for large-image performance.  Each pixel pair
    encodes a known luma value with neutral chroma (128), so the decoded
    RGB output equals ``(pixel_index % 256)`` for all three channels.
    """
    if width % 2:
        raise ValueError("width must be even")

    y_idx = np.arange(height, dtype=np.uint32).reshape(-1, 1)  # (H, 1)
    x_idx = np.arange(0, width, 2, dtype=np.uint32).reshape(1, -1)  # (1, W/2)

    luma = y_idx * width + x_idx  # (H, W/2)
    y0 = (luma % 256).astype(np.uint16)
    y1 = ((luma + 1) % 256).astype(np.uint16)
    neutral = np.full_like(y0, 128, dtype=np.uint16)

    data = np.empty((height, width), dtype=np.uint16)
    # YUYV little-endian: [Y0, U] → U<<8 | Y0,  [Y1, V] → V<<8 | Y1
    data[:, 0::2] = y0 | (neutral << 8)
    data[:, 1::2] = y1 | (neutral << 8)
    return data


def expected_rgb_from_luma(width: int, height: int) -> np.ndarray:
    """Expected RGB image for make_known_yuyv_tile's neutral chroma pattern."""
    expected_luma = np.arange(width * height, dtype=np.uint8).reshape(height, width)
    return np.repeat(expected_luma[:, :, np.newaxis], 3, axis=2)


def write_synthetic_33007_svs(
    path: Path,
    width: int = 16,
    height: int = 16,
    src_tile_size: int = 16,
    description: Optional[str] = None,
) -> None:
    """
    Write a tiled TIFF whose tile payload is raw YUYV, then patch compression.

    tifffile does not encode Aperio 33007. The production reader bypasses
    tifffile image decoding and reads tile byte ranges directly, so this
    fixture creates a valid tiled TIFF container with the exact raw tile bytes
    the decoder expects.

    Args:
        path: Destination file path.
        width: Image width in pixels (must be even).
        height: Image height in pixels.
        src_tile_size: Source tile dimension for the SVS container.
            Default 16 matches legacy test behaviour; use 256 for realistic
            large-fixture tests.
        description: TIFF ImageDescription tag value.  Defaults to
            ``"Aperio synthetic|MPP = 0.5"``.
    """
    if width % 2:
        raise ValueError("width must be even")
    if height <= 0:
        raise ValueError("height must be positive")
    if src_tile_size <= 0:
        raise ValueError("src_tile_size must be positive")

    if description is None:
        description = "Aperio synthetic|MPP = 0.5"

    # Use vectorised path for large images, fall back to legacy for tiny ones
    # to keep the original code path exercised.
    if max(width, height) <= 64:
        raw = make_known_yuyv_tile(width, height)
        data = np.frombuffer(raw, dtype="<u2").reshape(height, width)
    else:
        data = _make_synthetic_yuyv_data(width, height)

    with tifffile.TiffWriter(path) as tif:
        tif.write(
            data,
            tile=(src_tile_size, src_tile_size),
            photometric="minisblack",
            metadata=None,
            description=description,
        )

    with tifffile.TiffFile(path) as tif:
        compression_value_offset = tif.pages[0].tags["Compression"].valueoffset

    with path.open("r+b") as handle:
        handle.seek(compression_value_offset)
        handle.write(struct.pack("<H", 33007))
