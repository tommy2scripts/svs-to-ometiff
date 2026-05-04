"""
YUYV (YCbCr 4:2:2 interleaved) to RGB decoder using BT.601 full-range conversion.

Aperio compression tag 33007 stores tiles as raw YUYV planar YCbCr 4:2:2,
which is NOT standard JPEG or JPEG 2000. Each 2-pixel block is encoded as
4 bytes: [Y0, U, Y1, V]. This module decodes each tile to RGB.

Reference: ITU-R BT.601 (YCbCr to RGB, full-range, no headroom/footroom).
"""

import numpy as np


def yuyv_to_rgb(
    raw_bytes: bytes,
    tile_width: int = 256,
    tile_height: int = 256,
) -> np.ndarray:
    """
    Decode a single YUYV-encoded tile to an RGB image.

    The YUYV format packs each pair of adjacent pixels as 4 bytes:
        [Y0, U0, Y1, V0]
    Where Y0/Y1 are luma values and U0/V0 are shared chroma samples.

    Uses BT.601 full-range (0-255) conversion:
        R = Y + 1.402    * (Cr - 128)
        G = Y - 0.344136 * (Cb - 128) - 0.714136 * (Cr - 128)
        B = Y + 1.772    * (Cb - 128)

    Args:
        raw_bytes: Raw YUYV tile data (tile_height * tile_width * 2 bytes).
        tile_width: Width of the tile in pixels (default 256).
        tile_height: Height of the tile in pixels (default 256).

    Returns:
        RGB image as a numpy array of shape (tile_height, tile_width, 3),
        dtype uint8.

    Raises:
        ValueError: If dimensions are invalid or the byte count does not match
            the expected tile size.
    """
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError(
            "YUYV tile dimensions must be positive; "
            f"got {tile_width}x{tile_height}"
        )
    if tile_width % 2 != 0:
        raise ValueError(
            "YUYV 4:2:2 tiles require an even tile_width because each "
            f"chroma sample is shared by a 2-pixel pair; got {tile_width}"
        )

    expected_bytes = tile_width * tile_height * 2
    actual_bytes = len(raw_bytes)
    if actual_bytes != expected_bytes:
        raise ValueError(
            f"Expected {expected_bytes} bytes for {tile_width}x{tile_height} "
            f"YUYV tile (width * height * 2), got {actual_bytes}"
        )

    # Interpret as flat uint8 array
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)

    n_pixels = tile_width * tile_height
    n_pairs = n_pixels // 2

    # Reshape to (N/2, 4) where each row is [Y0, U, Y1, V]
    yuyv = arr.reshape(n_pairs, 4)

    # Extract planes as float32 for arithmetic
    Y0 = yuyv[:, 0].astype(np.float32)
    U = yuyv[:, 1].astype(np.float32)
    Y1 = yuyv[:, 2].astype(np.float32)
    V = yuyv[:, 3].astype(np.float32)

    # Apply BT.601 full-range YCbCr -> RGB to each pixel
    def _convert(y: np.ndarray, cb: np.ndarray, cr: np.ndarray) -> np.ndarray:
        """BT.601 full-range YCbCr -> RGB for a single pixel."""
        rgb_float = np.stack(
            [
                y + 1.402 * (cr - 128.0),
                y - 0.344136 * (cb - 128.0) - 0.714136 * (cr - 128.0),
                y + 1.772 * (cb - 128.0),
            ],
            axis=1,
        )
        return np.clip(rgb_float, 0, 255).astype(np.uint8)

    rgb0 = _convert(Y0, U, V)  # First pixel of each pair
    rgb1 = _convert(Y1, U, V)  # Second pixel of each pair

    # Interleave: [pixel0, pixel1, pixel0, pixel1, ...]
    rgb = np.empty((n_pixels, 3), dtype=np.uint8)
    rgb[0::2] = rgb0
    rgb[1::2] = rgb1

    return rgb.reshape(tile_height, tile_width, 3)
