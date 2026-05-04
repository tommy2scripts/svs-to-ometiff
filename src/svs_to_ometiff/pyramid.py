"""
Pyramid builder for multi-resolution OME-TIFF generation.

Creates a multi-level image pyramid from a full-resolution RGB image using
block-averaging downsampling.
"""

import time
from collections.abc import Callable
from typing import Literal, Optional

import numpy as np

ProgressLogger = Callable[[str], None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message)


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

    Args:
        full_image: Full-resolution RGB image (H, W, 3), uint8.
        num_levels: Number of pyramid levels including full resolution.
        downsample_factor: Factor by which each level is reduced (default 2).
        edge_mode: Border handling for non-divisible dimensions.
            "crop" drops trailing edge pixels (backward-compatible behavior).
            "pad" extends to the next multiple using edge-replication padding.
        verbose: Print progress information.
        progress_logger: Optional callable used instead of print.

    Returns:
        List of numpy arrays from level 0 (full res) to level N-1 (coarsest),
        each of shape (H_i, W_i, 3).

    Raises:
        ValueError: If inputs are invalid or requested levels cannot be built.
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

        # Reshape and average over factor×factor blocks
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
