"""
Programmatic conversion API for svs-to-ometiff.

The public ``convert`` function mirrors the CLI pipeline: read Aperio 33007
tiles, decode YUYV to RGB, build a pyramid, and write pyramidal OME-TIFF.
"""

import os
from collections.abc import Callable
from typing import Optional

import numpy as np

from svs_to_ometiff.pyramid import build_pyramid
from svs_to_ometiff.tile_reader import read_svs_full_image, read_svs_metadata
from svs_to_ometiff.writer import write_pyramidal_ometiff

ProgressLogger = Callable[[str], None]


def estimate_peak_ram_bytes(
    width: int,
    height: int,
    *,
    num_levels: int = 6,
    downsample_factor: int = 2,
) -> int:
    """
    Estimate peak resident RAM for full RGB image plus pyramid levels.

    This is intentionally conservative. The full-resolution image uses
    ``width * height * 3`` bytes, and the generated pyramid adds a geometric
    series of smaller RGB arrays. Temporary decoder arrays and TIFF buffers add
    additional overhead at runtime.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions must be positive, got {width}x{height}")
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )

    total_pixels = 0
    level_width = width
    level_height = height
    for _ in range(num_levels):
        total_pixels += level_width * level_height
        level_width = max(1, level_width // downsample_factor)
        level_height = max(1, level_height // downsample_factor)

    rgb_bytes = total_pixels * 3
    return int(rgb_bytes * 1.25)


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message)


def convert(
    input_svs: str,
    output_ometiff: str,
    *,
    tile_size: int = 512,
    compression: Optional[str] = "lzw",
    num_levels: int = 6,
    downsample_factor: int = 2,
    image_name: Optional[str] = None,
    verbose: bool = True,
    tile_progress_interval: int = 20,
    progress_logger: Optional[ProgressLogger] = None,
) -> dict[str, object]:
    """
    Convert Aperio compression-33007 SVS to pyramidal OME-TIFF.

    Args:
        input_svs: Source SVS path.
        output_ometiff: Destination OME-TIFF path.
        tile_size: Output OME-TIFF tile size.
        compression: TIFF compression name, or None for uncompressed output.
        num_levels: Number of pyramid levels including full resolution.
        downsample_factor: Downsampling factor between pyramid levels.
        image_name: OME image name. Defaults to input file stem.
        verbose: Emit progress messages.
        tile_progress_interval: Print tile-conversion progress every N source
            tile rows. Use 0 to suppress tile progress.
        progress_logger: Optional callable used instead of print.

    Returns:
        Metadata dict with input metadata, estimated peak RAM, pyramid shapes,
        and output file size.
    """
    if image_name is None:
        image_name = os.path.splitext(os.path.basename(input_svs))[0]

    metadata = read_svs_metadata(input_svs)
    if metadata["compression"] != 33007:
        raise ValueError(
            "svs-to-ometiff only supports Aperio compression 33007; "
            f"input uses compression {metadata['compression']}"
        )

    estimated_ram = estimate_peak_ram_bytes(
        int(metadata["width"]),
        int(metadata["height"]),
        num_levels=num_levels,
        downsample_factor=downsample_factor,
    )
    estimated_ram_gb = estimated_ram / 1e9

    _log(verbose, progress_logger, f"Reading SVS: {input_svs}")
    _log(verbose, progress_logger, f"Output: {output_ometiff}")
    _log(
        verbose,
        progress_logger,
        (
            f"Image: {metadata['width']} x {metadata['height']} px; "
            f"source tiles: {metadata['src_tile_width']}x"
            f"{metadata['src_tile_height']}, count={metadata['tile_count']}"
        ),
    )
    _log(verbose, progress_logger, f"Estimated peak RAM: {estimated_ram_gb:.1f} GB")
    if estimated_ram_gb > 30:
        _log(
            verbose,
            progress_logger,
            "WARNING: estimated peak RAM exceeds 30 GB; run on a high-memory host.",
        )

    full_image, metadata = read_svs_full_image(
        input_svs,
        progress_interval=tile_progress_interval if verbose else 0,
    )

    mpp = float(metadata["mpp"])
    _log(verbose, progress_logger, f"MPP: {mpp} um/px")
    _log(verbose, progress_logger, f"Building {num_levels}-level pyramid...")

    pyramid = build_pyramid(
        full_image,
        num_levels=num_levels,
        downsample_factor=downsample_factor,
        verbose=verbose,
    )

    del full_image

    _log(verbose, progress_logger, "Writing OME-TIFF...")
    write_pyramidal_ometiff(
        output_ometiff,
        pyramid,
        mpp,
        tile_size=tile_size,
        compression=compression,
        image_name=image_name,
        verbose=verbose,
    )

    output_size = os.path.getsize(output_ometiff)
    result: dict[str, object] = {
        **metadata,
        "estimated_peak_ram_bytes": estimated_ram,
        "pyramid_shapes": [tuple(np.asarray(level).shape) for level in pyramid],
        "output_path": output_ometiff,
        "output_size_bytes": output_size,
    }
    _log(
        verbose,
        progress_logger,
        f"Conversion complete: {output_ometiff} ({output_size / 1e9:.2f} GB)",
    )
    return result
