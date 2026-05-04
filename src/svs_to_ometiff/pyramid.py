"""
Pyramid builder for multi-resolution OME-TIFF generation.

Creates a 6-level image pyramid from a full-resolution RGB image using
2× block-averaging downsampling. This produces excellent quality for
pathology images and is fast compared to interpolation-based methods.
"""

import time

import numpy as np


def build_pyramid(
    full_image: np.ndarray,
    num_levels: int = 6,
    downsample_factor: int = 2,
    *,
    verbose: bool = True,
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
        verbose: Print progress information.

    Returns:
        List of numpy arrays from level 0 (full res) to level N-1 (coarsest),
        each of shape (H_i, W_i, 3).

    Raises:
        ValueError: If num_levels < 1 or image dimensions are too small.
    """
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")

    h, w = full_image.shape[:2]
    if h < downsample_factor or w < downsample_factor:
        raise ValueError(
            f"Image ({w}x{h}) too small for downsampling by {downsample_factor}"
        )

    t0 = time.time()

    pyramid: list[np.ndarray] = [full_image]

    for level in range(1, num_levels):
        prev = pyramid[-1]
        factor = downsample_factor

        # Crop to multiples of the downsample factor
        new_h = prev.shape[0] // factor
        new_w = prev.shape[1] // factor
        crop_h = new_h * factor
        crop_w = new_w * factor

        # Reshape and average over factor×factor blocks
        cropped = prev[:crop_h, :crop_w]
        downsampled = (
            cropped.reshape(new_h, factor, new_w, factor, 3)
            .mean(axis=(1, 3))
            .astype(np.uint8)
        )

        pyramid.append(downsampled)

        if verbose:
            print(
                f"  Level {level}: "
                f"{downsampled.shape[1]} x {downsampled.shape[0]} px"
            )

    if verbose:
        print(f"Pyramid built in {time.time() - t0:.0f}s")

    return pyramid
