"""
Pyramid builder for multi-resolution OME-TIFF generation.

Creates multi-level image pyramids from full-resolution RGB images using
block-averaging downsampling. The classic API returns in-memory arrays; the
streaming conversion path uses disk-backed memmaps for lower peak RAM.
"""

import gc
import logging
import shutil
import time
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from svs_to_ometiff.utils import ProgressLogger, _log


def build_pyramid(
    full_image: np.ndarray,
    num_levels: int = 6,
    downsample_factor: int = 2,
    edge_mode: Literal["crop", "pad"] = "crop",
    *,
    verbose: bool = True,
    progress_logger: Optional[ProgressLogger] = None,
) -> list[np.ndarray]:
    """
    Build a multi-resolution pyramid by iterative block averaging.

    Each level is created by averaging non-overlapping blocks of
    `downsample_factor × downsample_factor` pixels from the previous level.
    Edge pixels are dropped if dimensions are not divisible by the factor.
    """
    if full_image.ndim != 3 or full_image.shape[2] != 3:
        raise ValueError(f"full_image must have shape (H, W, 3), got {full_image.shape}")
    if full_image.dtype != np.uint8:
        raise ValueError(f"full_image must be uint8, got {full_image.dtype}")
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )
    if edge_mode not in {"crop", "pad"}:
        raise ValueError(f"edge_mode must be 'crop' or 'pad', got {edge_mode!r}")

    h, w = full_image.shape[:2]
    if num_levels > 1 and (h < downsample_factor or w < downsample_factor):
        raise ValueError(
            f"Image ({w}x{h}) too small for downsampling by {downsample_factor}"
        )

    t0 = time.time()

    pyramid: list[np.ndarray] = [full_image]

    for level in range(1, num_levels):
        prev = pyramid[-1]
        factor = downsample_factor

        if edge_mode == "crop":
            new_h = prev.shape[0] // factor
            new_w = prev.shape[1] // factor
        else:
            new_h = (prev.shape[0] + factor - 1) // factor
            new_w = (prev.shape[1] + factor - 1) // factor
        if new_h < 1 or new_w < 1:
            raise ValueError(
                f"Cannot build level {level}: previous level "
                f"{prev.shape[1]}x{prev.shape[0]} is too small for "
                f"downsampling by {factor}"
            )
        crop_h = new_h * factor
        crop_w = new_w * factor

        if edge_mode == "crop":
            cropped = prev[:crop_h, :crop_w]
        else:
            pad_h = crop_h - prev.shape[0]
            pad_w = crop_w - prev.shape[1]
            cropped = np.pad(prev, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
        downsampled = (
            cropped.reshape(new_h, factor, new_w, factor, 3)
            .mean(axis=(1, 3))
            .astype(np.uint8)
        )

        pyramid.append(downsampled)

        _log(
            verbose,
            progress_logger,
            f"  Level {level}: {downsampled.shape[1]} x {downsampled.shape[0]} px",
        )

    _log(verbose, progress_logger, f"Pyramid built in {time.time() - t0:.0f}s")

    return pyramid


def _next_level_shape(
    height: int,
    width: int,
    factor: int,
    edge_mode: Literal["crop", "pad"],
) -> tuple[int, int]:
    if edge_mode == "crop":
        return height // factor, width // factor
    return (height + factor - 1) // factor, (width + factor - 1) // factor


def build_pyramid_memmaps(
    base_level: np.ndarray,
    temp_dir: str,
    *,
    num_levels: int = 6,
    downsample_factor: int = 2,
    edge_mode: Literal["crop", "pad"] = "crop",
    verbose: bool = True,
    progress_logger: Optional[ProgressLogger] = None,
) -> list[np.ndarray]:
    """
    Build lower pyramid levels as disk-backed memmaps.

    ``base_level`` is included as level 0 and is not copied. Each lower level is
    generated row-by-row from the previous level, keeping only a small strip in
    RAM instead of materializing the full pyramid as heap arrays.
    """
    if base_level.ndim != 3 or base_level.shape[2] != 3:
        raise ValueError(f"base_level must have shape (H, W, 3), got {base_level.shape}")
    if base_level.dtype != np.uint8:
        raise ValueError(f"base_level must be uint8, got {base_level.dtype}")
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )
    if edge_mode not in {"crop", "pad"}:
        raise ValueError(f"edge_mode must be 'crop' or 'pad', got {edge_mode!r}")

    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    levels: list[np.ndarray] = [base_level]
    factor = downsample_factor
    t0 = time.time()

    for level_index in range(1, num_levels):
        prev = levels[-1]
        prev_h, prev_w = prev.shape[:2]
        new_h, new_w = _next_level_shape(prev_h, prev_w, factor, edge_mode)
        if new_h < 1 or new_w < 1:
            raise ValueError(
                f"Cannot build level {level_index}: previous level "
                f"{prev_w}x{prev_h} is too small for downsampling by {factor}"
            )

        path = str(Path(temp_dir) / f"pyramid_level_{level_index}.dat")
        dest = np.memmap(path, dtype=np.uint8, mode="w+", shape=(new_h, new_w, 3))
        crop_w = new_w * factor

        # Pre-allocate a buffer for padding if needed to avoid repeated np.pad allocations.
        pad_buffer = None
        if edge_mode == "pad" and (prev_h % factor != 0 or prev_w % factor != 0):
            pad_buffer = np.empty((factor, crop_w, 3), dtype=np.uint8)

        for y in range(new_h):
            src_y0 = y * factor
            src_y1 = min(src_y0 + factor, prev_h)
            src_x1 = min(crop_w, prev_w)
            strip = prev[src_y0:src_y1, :src_x1]

            if edge_mode == "pad" and (
                strip.shape[0] != factor or strip.shape[1] != crop_w
            ):
                h_small, w_small = strip.shape[:2]
                pad_buffer[:h_small, :w_small] = strip
                if h_small < factor:
                    pad_buffer[h_small:, :w_small] = strip[h_small - 1 : h_small, :]
                if w_small < crop_w:
                    pad_buffer[:, w_small:] = pad_buffer[:, w_small - 1 : w_small]
                strip = pad_buffer

            dest[y] = (
                strip.reshape(factor, new_w, factor, 3)
                .mean(axis=(0, 2))
                .astype(np.uint8)
            )

        dest.flush()
        levels.append(dest)
        _log(
            verbose,
            progress_logger,
            f"  Level {level_index}: {new_w} x {new_h} px",
        )

    _log(verbose, progress_logger, f"Pyramid built in {time.time() - t0:.0f}s")
    return levels

# Maximum seconds to spend retrying temp directory cleanup
_CLEANUP_RETRY_DELAYS = [0.5, 1.0, 2.0]


def close_memmap_array(arr: np.ndarray) -> None:
    """Flush and close a numpy memmap without failing for regular arrays."""
    if not isinstance(arr, np.memmap):
        return

    try:
        arr.flush()
    except Exception:
        pass

    mmap_obj = getattr(arr, "_mmap", None)
    if mmap_obj is not None:
        try:
            mmap_obj.close()
        except Exception:
            pass


def cleanup_pyramid_memmaps(
    levels: list[np.ndarray],
    temp_dir: str,
    *,
    max_retries: int = 3,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Safely close memmaps and remove temp directory with Windows-friendly retry logic.

    Args:
        levels: List of numpy arrays (some may be memmaps) to close.
        temp_dir: Temporary directory to remove.
        max_retries: Number of cleanup retries (default 3).
        logger: Optional logger for warnings.

    Returns:
        Warning message if cleanup failed, None if successful.
    """
    # 1. Flush and close all memmaps explicitly
    for level in levels:
        close_memmap_array(level)
    levels.clear()

    # 2. Run GC to release any file handles
    gc.collect()

    # 3. Retry directory removal with backoff
    for attempt in range(max_retries + 1):
        try:
            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
            return None
        except PermissionError:
            if attempt < max_retries:
                time.sleep(_CLEANUP_RETRY_DELAYS[min(attempt, len(_CLEANUP_RETRY_DELAYS) - 1)])
                gc.collect()
                continue
            msg = (
                f"Temp directory cleanup failed after {max_retries} retries: "
                f"{temp_dir}. The output OME-TIFF was written successfully "
                f"but temporary files could not be removed. "
                f"You may safely delete the temp folder manually."
            )
            if logger:
                logger.warning(msg)
            else:
                log = logging.getLogger(__name__)
                log.warning(msg)
            return msg
        except Exception as exc:
            msg = f"Temp directory cleanup warning: {exc}. Temp dir: {temp_dir}"
            if logger:
                logger.warning(msg)
            else:
                log = logging.getLogger(__name__)
                log.warning(msg)
            return msg
    return None
