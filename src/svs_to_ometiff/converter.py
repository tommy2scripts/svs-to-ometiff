"""
Programmatic conversion API for svs-to-ometiff.

The public ``convert`` function mirrors the CLI pipeline: read Aperio 33007
tiles, decode YUYV to RGB, build a pyramid, and write pyramidal OME-TIFF.
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff.pyramid import build_pyramid_memmaps
from svs_to_ometiff.tile_reader import iter_svs_rgb_tiles, read_svs_metadata
from svs_to_ometiff.utils import _log
from svs_to_ometiff.writer import (
    write_pyramidal_ometiff_from_levels as write_pyramidal_ometiff,
)


_LEGACY_CONFIG_DEFAULTS: dict[str, object] = {
    "tile_size": 512,
    "compression": None,
    "num_levels": 3,
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
    Estimate peak resident RAM for the streaming/out-of-core conversion path.

    The optimized path stages full-resolution and lower pyramid levels on disk
    as memmaps, so expected heap/RSS pressure is dominated by source tiles,
    downsampling strips, TIFF writer tile buffers, and OS page-cache behavior.
    The estimate intentionally tracks the validation target of roughly 1.2x the
    full-resolution RGB byte count rather than the old full-pyramid footprint.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions must be positive, got {width}x{height}")
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )

    return int(width * height * 3 * 1.2)


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


def _close_memmaps(levels: list[np.ndarray]) -> None:
    for level in levels:
        if isinstance(level, np.memmap):
            level.flush()
            mmap = getattr(level, "_mmap", None)
            if mmap is not None:
                mmap.close()


def _stage_level0_memmap(
    config: ConvertConfig,
    metadata: dict[str, object],
    temp_dir: str,
) -> np.memmap:
    height = int(metadata["height"])
    width = int(metadata["width"])
    path = str(Path(temp_dir) / "pyramid_level_0.dat")
    level0 = np.memmap(path, dtype=np.uint8, mode="w+", shape=(height, width, 3))

    for item in iter_svs_rgb_tiles(
        config.input_svs,
        progress_interval=config.tile_progress_interval if config.verbose else 0,
        progress_logger=config.progress_logger,
    ):
        y0 = item["y0"]
        y1 = item["y1"]
        x0 = item["x0"]
        x1 = item["x1"]
        tile_rgb = item["tile"]
        level0[y0:y1, x0:x1] = tile_rgb[: y1 - y0, : x1 - x0]

    level0.flush()
    return level0


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
        image_name = Path(config.input_svs).stem

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

    _log(config.verbose, config.progress_logger, f"Reading SVS: {config.input_svs}", phase="setup", percent=5.0)
    _log(config.verbose, config.progress_logger, f"Output: {config.output_ometiff}", phase="setup", percent=5.0)
    _log(
        config.verbose,
        config.progress_logger,
        (
            f"Image: {metadata['width']} x {metadata['height']} px; "
            f"source tiles: {metadata['src_tile_width']}x"
            f"{metadata['src_tile_height']}, count={metadata['tile_count']}"
        ),
        phase="setup",
        percent=5.0,
    )
    _log(
        config.verbose,
        config.progress_logger,
        f"Estimated streaming peak RAM target: {estimated_ram_gb:.1f} GB",
    )
    if estimated_ram_gb > 30:
        _log(
            config.verbose,
            config.progress_logger,
            "WARNING: estimated peak RAM exceeds 30 GB; run on a high-memory host.",
        )

    output_dir = str(Path(config.output_ometiff).resolve().parent) or None
    levels: list[np.ndarray] = []
    with tempfile.TemporaryDirectory(prefix="svs_to_ometiff_", dir=output_dir) as temp_dir:
        _log(config.verbose, config.progress_logger, "Decoding SVS tiles to disk-backed level 0...", phase="tile_decoding", percent=10.0)
        level0 = _stage_level0_memmap(config, metadata, temp_dir)

        mpp = float(metadata["mpp"])
        magnification = metadata.get("magnification")
        _log(config.verbose, config.progress_logger, f"MPP: {mpp} um/px")
        if magnification is not None:
            _log(
                config.verbose,
                config.progress_logger,
                f"Magnification: {int(magnification) if magnification == int(magnification) else magnification}X",
            )
        _log(
            config.verbose,
            config.progress_logger,
            f"Building {config.num_levels}-level pyramid out of core...",
            phase="pyramid_building",
            percent=62.0,
        )

        levels = build_pyramid_memmaps(
            level0,
            temp_dir,
            num_levels=config.num_levels,
            downsample_factor=config.downsample_factor,
            edge_mode=config.edge_mode,
            verbose=config.verbose,
            progress_logger=config.progress_logger,
        )
        pyramid_shapes = [tuple(np.asarray(level).shape) for level in levels]

        _log(config.verbose, config.progress_logger, "Writing OME-TIFF...", phase="writing_ometiff", percent=86.0)
        try:
            write_pyramidal_ometiff(
                config.output_ometiff,
                levels,
                mpp,
                tile_size=config.tile_size,
                compression=config.compression,
                image_name=image_name,
                magnification=magnification,
                verbose=config.verbose,
                progress_logger=config.progress_logger,
            )
        except Exception as exc:
            _raise_write_error_with_context(exc, config.compression)
        finally:
            _close_memmaps(levels)

    output_size = Path(config.output_ometiff).stat().st_size
    result: dict[str, object] = {
        **metadata,
        "estimated_peak_ram_bytes": estimated_ram,
        "pyramid_shapes": pyramid_shapes,
        "output_path": config.output_ometiff,
        "output_size_bytes": output_size,
    }
    _log(
        config.verbose,
        config.progress_logger,
        f"Conversion complete: {config.output_ometiff} ({output_size / 1e9:.2f} GB)",
        phase="complete",
        percent=100.0,
    )
    return result
