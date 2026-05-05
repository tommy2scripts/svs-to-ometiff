"""
Programmatic conversion API for svs-to-ometiff.

The public ``convert`` function mirrors the CLI pipeline: read Aperio 33007
tiles, decode YUYV to RGB, build a pyramid, and write pyramidal OME-TIFF.
"""

import os
from typing import Any, Optional, Union

import numpy as np

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff.pyramid import build_pyramid
from svs_to_ometiff.tile_reader import read_svs_full_image, read_svs_metadata
from svs_to_ometiff.utils import _log
from svs_to_ometiff.writer import write_pyramidal_ometiff


_LEGACY_CONFIG_DEFAULTS: dict[str, object] = {
    "tile_size": 512,
    "compression": "lzw",
    "num_levels": 6,
    "downsample_factor": 2,
    "edge_mode": "crop",
    "image_name": None,
    "verbose": True,
    "tile_progress_interval": 20,
    "progress_logger": None,
}


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


def _coerce_convert_config(
    config_or_input_svs: Union[ConvertConfig, str],
    output_ometiff: Optional[str],
    legacy_kwargs: dict[str, Any],
) -> ConvertConfig:
    if isinstance(config_or_input_svs, ConvertConfig):
        if output_ometiff is not None or legacy_kwargs:
            raise TypeError(
                "convert() accepts either a ConvertConfig or legacy "
                "input/output arguments, not both"
            )
        return config_or_input_svs

    if output_ometiff is None:
        raise TypeError("convert() missing required output_ometiff argument")

    unknown = sorted(set(legacy_kwargs) - set(_LEGACY_CONFIG_DEFAULTS))
    if unknown:
        unknown_args = ", ".join(unknown)
        raise TypeError(f"convert() got unexpected keyword argument(s): {unknown_args}")

    values = {**_LEGACY_CONFIG_DEFAULTS, **legacy_kwargs}
    return ConvertConfig(
        input_svs=config_or_input_svs,
        output_ometiff=output_ometiff,
        **values,
    )


def _raise_write_error_with_context(exc: Exception, compression: Optional[str]) -> None:
    message = str(exc)
    message_lower = message.lower()

    if isinstance(exc, KeyError) and "imagecodecs" in message_lower:
        raise RuntimeError(
            "Failed to write compressed OME-TIFF because imagecodecs is missing "
            "or unavailable. Install it with 'pip install imagecodecs'. If the "
            "compressed write still fails, retry with '--compression none'."
        ) from exc

    compression_error_tokens = (
        "compression",
        "compressor",
        "encode",
        "codec",
        "imagecodecs",
    )
    if compression is not None and any(
        token in message_lower for token in compression_error_tokens
    ):
        raise RuntimeError(
            f"Failed to write OME-TIFF with compression {compression!r}: {message}. "
            "Retry with '--compression none' to write uncompressed output."
        ) from exc

    raise exc


def convert(
    config_or_input_svs: Union[ConvertConfig, str],
    output_ometiff: Optional[str] = None,
    **legacy_kwargs: Any,
) -> dict[str, object]:
    """
    Convert Aperio compression-33007 SVS to pyramidal OME-TIFF.

    Args:
        config_or_input_svs: Preferred form is a :class:`ConvertConfig`.
            For backwards compatibility, callers may still pass the source SVS
            path here and the destination path as ``output_ometiff``.
        output_ometiff: Destination OME-TIFF path for legacy callers.
        **legacy_kwargs: Conversion options for legacy callers. New code should
            put these values on ``ConvertConfig``.

    Returns:
        Metadata dict with input metadata, estimated peak RAM, pyramid shapes,
        and output file size.
    """
    config = _coerce_convert_config(
        config_or_input_svs,
        output_ometiff,
        legacy_kwargs,
    )

    image_name = config.image_name
    if image_name is None:
        image_name = os.path.splitext(os.path.basename(config.input_svs))[0]

    metadata = read_svs_metadata(config.input_svs)
    if metadata["compression"] != 33007:
        raise ValueError(
            "svs-to-ometiff only supports Aperio compression 33007; "
            f"input uses compression {metadata['compression']}"
        )

    estimated_ram = estimate_peak_ram_bytes(
        int(metadata["width"]),
        int(metadata["height"]),
        num_levels=config.num_levels,
        downsample_factor=config.downsample_factor,
    )
    estimated_ram_gb = estimated_ram / 1e9

    _log(config.verbose, config.progress_logger, f"Reading SVS: {config.input_svs}")
    _log(config.verbose, config.progress_logger, f"Output: {config.output_ometiff}")
    _log(
        config.verbose,
        config.progress_logger,
        (
            f"Image: {metadata['width']} x {metadata['height']} px; "
            f"source tiles: {metadata['src_tile_width']}x"
            f"{metadata['src_tile_height']}, count={metadata['tile_count']}"
        ),
    )
    _log(
        config.verbose,
        config.progress_logger,
        f"Estimated peak RAM: {estimated_ram_gb:.1f} GB",
    )
    if estimated_ram_gb > 30:
        _log(
            config.verbose,
            config.progress_logger,
            "WARNING: estimated peak RAM exceeds 30 GB; run on a high-memory host.",
        )

    full_image, metadata = read_svs_full_image(
        config.input_svs,
        progress_interval=config.tile_progress_interval if config.verbose else 0,
    )

    mpp = float(metadata["mpp"])
    _log(config.verbose, config.progress_logger, f"MPP: {mpp} um/px")
    _log(
        config.verbose,
        config.progress_logger,
        f"Building {config.num_levels}-level pyramid...",
    )

    pyramid = build_pyramid(
        full_image,
        num_levels=config.num_levels,
        downsample_factor=config.downsample_factor,
        edge_mode=config.edge_mode,
        verbose=config.verbose,
        progress_logger=config.progress_logger,
    )

    del full_image

    _log(config.verbose, config.progress_logger, "Writing OME-TIFF...")
    try:
        write_pyramidal_ometiff(
            config.output_ometiff,
            pyramid,
            mpp,
            tile_size=config.tile_size,
            compression=config.compression,
            image_name=image_name,
            verbose=config.verbose,
            progress_logger=config.progress_logger,
        )
    except Exception as exc:
        _raise_write_error_with_context(exc, config.compression)

    output_size = os.path.getsize(config.output_ometiff)
    result: dict[str, object] = {
        **metadata,
        "estimated_peak_ram_bytes": estimated_ram,
        "pyramid_shapes": [tuple(np.asarray(level).shape) for level in pyramid],
        "output_path": config.output_ometiff,
        "output_size_bytes": output_size,
    }
    _log(
        config.verbose,
        config.progress_logger,
        f"Conversion complete: {config.output_ometiff} ({output_size / 1e9:.2f} GB)",
    )
    return result
