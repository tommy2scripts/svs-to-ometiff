"""Disk-space preflight estimation for SVS to OME-TIFF conversion."""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class PreflightError(RuntimeError):
    """Raised when disk preflight checks fail."""


@dataclass(frozen=True)
class PreflightResult:
    """Disk-space estimate and availability for one planned conversion."""

    source_width: int
    source_height: int
    full_res_rgb_bytes: int
    pyramid_rgb_bytes: int
    required_temp_bytes: int
    required_output_bytes: int
    available_temp_bytes: int
    available_output_bytes: int
    safety_factor: float
    pass_: bool
    errors: list[str]


DiskUsageFn = Callable[[str], tuple[int, int, int]]


def estimate_full_res_rgb_bytes(*, width: int, height: int) -> int:
    """Estimate bytes for one full-resolution uint8 RGB image."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions must be positive, got {width}x{height}")
    return width * height * 3


def estimate_pyramid_rgb_bytes(
    *,
    width: int,
    height: int,
    num_levels: int,
    downsample_factor: int,
) -> int:
    """Estimate total uint8 RGB bytes across all requested pyramid levels."""
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )

    total = 0
    level_width = width
    level_height = height
    for _ in range(num_levels):
        total += estimate_full_res_rgb_bytes(width=level_width, height=level_height)
        level_width = max(1, math.ceil(level_width / downsample_factor))
        level_height = max(1, math.ceil(level_height / downsample_factor))
    return total


def bytes_to_gb(value: int) -> float:
    """Return decimal GB for user-facing estimates."""
    return value / 1e9


def _format_gb(value: int) -> str:
    return f"{bytes_to_gb(value):.1f} GB"


def check_preflight(
    *,
    width: int,
    height: int,
    output_path: str | Path,
    temp_dir: str | Path,
    num_levels: int,
    downsample_factor: int,
    safety_factor: float,
    disk_usage: DiskUsageFn = shutil.disk_usage,
) -> PreflightResult:
    """Estimate disk requirements and raise ``PreflightError`` if insufficient."""
    if safety_factor <= 0:
        raise ValueError(f"safety_factor must be positive, got {safety_factor}")

    output = Path(output_path)
    output_parent = output.parent if output.parent.name else Path.cwd()
    temp = Path(temp_dir)
    output_parent.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)

    full_res_bytes = estimate_full_res_rgb_bytes(width=width, height=height)
    pyramid_bytes = estimate_pyramid_rgb_bytes(
        width=width,
        height=height,
        num_levels=num_levels,
        downsample_factor=downsample_factor,
    )
    required_temp = math.ceil(pyramid_bytes * safety_factor)
    required_output = math.ceil(pyramid_bytes * safety_factor)
    available_temp = int(disk_usage(str(temp))[2])
    available_output = int(disk_usage(str(output_parent))[2])

    errors: list[str] = []
    if available_temp < required_temp:
        errors.append(
            "Insufficient temp space. "
            f"Required ~{_format_gb(required_temp)}, "
            f"available {_format_gb(available_temp)}. "
            "Use --temp-dir on a larger local SSD."
        )
    if available_output < required_output:
        errors.append(
            "Insufficient output space. "
            f"Required ~{_format_gb(required_output)}, "
            f"available {_format_gb(available_output)}. "
            "Choose an output directory on a larger drive."
        )

    result = PreflightResult(
        source_width=width,
        source_height=height,
        full_res_rgb_bytes=full_res_bytes,
        pyramid_rgb_bytes=pyramid_bytes,
        required_temp_bytes=required_temp,
        required_output_bytes=required_output,
        available_temp_bytes=available_temp,
        available_output_bytes=available_output,
        safety_factor=safety_factor,
        pass_=not errors,
        errors=errors,
    )
    if errors:
        raise PreflightError("\n".join(errors))
    return result
