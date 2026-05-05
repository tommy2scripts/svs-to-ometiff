from collections.abc import Callable
from typing import Optional

ProgressLogger = Callable[[str], None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message)
