"""
General-purpose utilities for svs-to-ometiff.
"""

import sys
from collections.abc import Callable
from typing import Any, Optional

ProgressLogger = Callable[..., None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str, **kwargs: Any) -> None:
    if not verbose:
        return
    if logger is None:
        print(message, file=sys.stderr, flush=True)
    else:
        logger(message, **kwargs)
