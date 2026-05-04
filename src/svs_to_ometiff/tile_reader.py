"""
Tile reader for Aperio SVS files with compression 33007 (YUYV).

Reads all 256x256 YUYV-encoded tiles from an SVS file and reassembles
the full-resolution RGB image in memory. Handles edge tiles that may
be smaller than 256x256 due to image dimensions not being multiples
of the tile size.
"""

import math
import time
from typing import Any

import numpy as np
import tifffile

from svs_to_ometiff.yuyv_decoder import yuyv_to_rgb


def read_svs_metadata(svs_path: str) -> dict[str, Any]:
    """
    Read first-page geometry and Aperio metadata without decoding image tiles.

    Args:
        svs_path: Path to the Aperio SVS file.

    Returns:
        Metadata dict with image dimensions, source tile geometry, tile count,
        MPP, and compression tag value.

    Raises:
        ValueError: If required SVS metadata is missing or inconsistent.
        tifffile.TiffFileError: If the file cannot be parsed as TIFF.
    """
    with tifffile.TiffFile(svs_path) as tif:
        page0 = tif.pages[0]
        img_h, img_w = page0.shape[:2]
        src_tile_h = page0.tilelength
        src_tile_w = page0.tilewidth

        if src_tile_h is None or src_tile_w is None:
            raise ValueError("Input SVS must be tiled; page 0 is not tiled")

        offsets = list(page0.dataoffsets)
        bytecounts = list(page0.databytecounts)
        desc = page0.tags["ImageDescription"].value
        mpp = parse_mpp_from_description(desc)
        compression = int(page0.tags["Compression"].value)

    n_tiles_x = math.ceil(img_w / src_tile_w)
    n_tiles_y = math.ceil(img_h / src_tile_h)
    total_tiles = n_tiles_x * n_tiles_y

    if len(offsets) != total_tiles:
        raise ValueError(
            f"Tile count mismatch: expected {total_tiles} from grid "
            f"({n_tiles_x}x{n_tiles_y}), got {len(offsets)} from file"
        )

    return {
        "mpp": mpp,
        "width": img_w,
        "height": img_h,
        "src_tile_width": src_tile_w,
        "src_tile_height": src_tile_h,
        "tile_count": total_tiles,
        "n_tiles_x": n_tiles_x,
        "n_tiles_y": n_tiles_y,
        "compression": compression,
        "bytecounts": bytecounts,
    }


def parse_mpp_from_description(description: str) -> float:
    """
    Extract microns-per-pixel (MPP) from an Aperio ImageDescription string.

    The description contains pipe-delimited fields including:
        MPP = 0.275310798315331

    Args:
        description: The ImageDescription tag value from the SVS.

    Returns:
        MPP value as a float.

    Raises:
        ValueError: If MPP cannot be parsed from the description.
    """
    for part in description.split("|"):
        part = part.strip()
        if part.startswith("MPP"):
            try:
                return float(part.split("=")[1].strip())
            except (IndexError, ValueError) as exc:
                raise ValueError(
                    f"Could not parse MPP from description field: {part}"
                ) from exc
    raise ValueError("MPP not found in ImageDescription tag")


def read_svs_full_image(
    svs_path: str,
    *,
    progress_interval: int = 20,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    Read all tiles from an SVS file and assemble the full-resolution RGB image.

    Decodes every tile using the YUYV decoder and places it at the correct
    position in the output image. Edge tiles are cropped to fit within the
    actual image dimensions.

    IMPORTANT: The full-resolution image can be large (e.g., ~4.5 GB for a
    39,599×39,858 image). Ensure sufficient RAM is available before calling.

    Args:
        svs_path: Path to the Aperio SVS file.
        progress_interval: Print progress every N tile rows (0 to suppress).

    Returns:
        Tuple of (full_image, metadata) where:
          - full_image: uint8 numpy array of shape (height, width, 3).
          - metadata: dict with keys 'mpp', 'width', 'height',
            'src_tile_width', 'src_tile_height', 'tile_count',
            'n_tiles_x', 'n_tiles_y'.

    Raises:
        ValueError: If the file is not a valid SVS or has unexpected structure.
        IOError: If the file cannot be read.
    """
    t_start = time.time()

    metadata = read_svs_metadata(svs_path)
    img_w = metadata["width"]
    img_h = metadata["height"]
    src_tile_w = metadata["src_tile_width"]
    src_tile_h = metadata["src_tile_height"]
    n_tiles_x = metadata["n_tiles_x"]
    n_tiles_y = metadata["n_tiles_y"]
    total_tiles = metadata["tile_count"]

    # Build tile index lookup: (row, col) -> linear index
    tile_idx = {}
    for ty in range(n_tiles_y):
        for tx in range(n_tiles_x):
            tile_idx[(ty, tx)] = ty * n_tiles_x + tx

    # Allocate full image
    full_img = np.zeros((img_h, img_w, 3), dtype=np.uint8)

    # Re-open for reading (filehandle may be closed after context manager)
    with tifffile.TiffFile(svs_path) as tif:
        page0 = tif.pages[0]
        offsets = list(page0.dataoffsets)
        bytecounts = list(page0.databytecounts)
        fh = tif.filehandle

        for ty in range(n_tiles_y):
            if progress_interval > 0 and ty % progress_interval == 0:
                elapsed = time.time() - t_start
                pct = 100 * ty / n_tiles_y
                print(
                    f"  Row {ty}/{n_tiles_y} ({pct:.0f}%) - {elapsed:.0f}s elapsed"
                )

            y0 = ty * src_tile_h
            y1 = min(y0 + src_tile_h, img_h)

            for tx in range(n_tiles_x):
                x0 = tx * src_tile_w
                x1 = min(x0 + src_tile_w, img_w)

                idx = tile_idx[(ty, tx)]
                fh.seek(offsets[idx])
                raw = fh.read(bytecounts[idx])
                tile_rgb = yuyv_to_rgb(raw, src_tile_w, src_tile_h)

                # Place tile, cropping to image bounds (handles edge tiles)
                full_img[y0:y1, x0:x1] = tile_rgb[: y1 - y0, : x1 - x0]

    elapsed = time.time() - t_start
    if progress_interval > 0:
        print(f"Full image read in {elapsed:.0f}s")
        print(f"Image shape: {full_img.shape}, dtype: {full_img.dtype}")

    return full_img, metadata
