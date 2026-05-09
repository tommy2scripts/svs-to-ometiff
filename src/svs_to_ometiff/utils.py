"""
General-purpose utilities for svs-to-ometiff.
"""

from collections.abc import Callable
from typing import Any, Optional

ProgressLogger = Callable[..., None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str, **kwargs: Any) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message, **kwargs)
