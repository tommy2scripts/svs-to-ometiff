"""
General-purpose utilities for svs-to-ometiff.
"""

from collections.abc import Callable
from typing import Literal, Optional

ProgressLogger = Callable[[str], None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message)


def validate_pyramid_params(
    num_levels: int,
    downsample_factor: int,
    edge_mode: Optional[Literal["crop", "pad"]] = None,
) -> None:
    """
    Validate shared pyramid parameters.

    Args:
        num_levels: Number of pyramid levels to create (must be >= 1).
        downsample_factor: Factor to downsample by (must be >= 2).
        edge_mode: Edge handling mode ('crop' or 'pad'). If None, skip validation.
    """
    if num_levels < 1:
        raise ValueError(f"num_levels must be at least 1, got {num_levels}")
    if downsample_factor < 2:
        raise ValueError(
            f"downsample_factor must be at least 2, got {downsample_factor}"
        )
    if edge_mode is not None and edge_mode not in {"crop", "pad"}:
        raise ValueError(f"edge_mode must be 'crop' or 'pad', got {edge_mode!r}")
