"""Configuration objects for svs-to-ometiff conversion."""

import json
import os

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal, Optional

from svs_to_ometiff.utils import ProgressLogger

_SUPPORTED_COMPRESSION = (None, "lzw", "zlib", "deflate", "jpeg", "jpeg2000")


@dataclass(frozen=True)
class ConvertConfig:
    """Inputs and options for :func:`svs_to_ometiff.converter.convert`."""

    input_svs: str
    output_ometiff: str
    tile_size: int = 1024
    compression: Optional[str] = "zlib"
    num_levels: int = 6
    downsample_factor: int = 2
    edge_mode: Literal["crop", "pad"] = "crop"
    image_name: Optional[str] = None
    verbose: bool = True
    tile_progress_interval: int = 20
    progress_logger: Optional[ProgressLogger] = None
    temp_dir: Optional[str] = None
    compressionargs: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        # Normalize "none" → None before validation
        if self.compression == "none":
            object.__setattr__(self, "compression", None)
        self._validate()

    def to_dict(self) -> dict[str, Any]:
        """Return serializable fields as a plain dict (excludes *progress_logger*)."""
        result: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "progress_logger":
                continue
            result[f.name] = getattr(self, f.name)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConvertConfig":
        """Build a ConvertConfig from a dict, using class defaults for missing fields.

        Unknown keys are silently ignored.  Validation (tile_size, compression,
        etc.) runs via the constructor's ``__post_init__``.

        If *compressionargs* is a JSON string it is parsed to a ``dict``.
        """
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        if "compressionargs" in filtered and isinstance(filtered["compressionargs"], str):
            try:
                filtered["compressionargs"] = json.loads(filtered["compressionargs"])
            except json.JSONDecodeError:
                pass
        return cls(**filtered)

    def _validate(self) -> None:
        input_path = Path(self.input_svs)
        output_path = Path(self.output_ometiff)
        if _paths_refer_to_same_file(input_path, output_path):
            raise ValueError("output_ometiff must be different from input_svs")
        if self.tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if self.tile_size % 16 != 0:
            raise ValueError("tile_size must be divisible by 16")
        if self.num_levels < 1:
            raise ValueError("num_levels must be at least 1")
        if self.downsample_factor < 2:
            raise ValueError("downsample_factor must be at least 2")
        if self.edge_mode not in {"crop", "pad"}:
            raise ValueError(f"edge_mode must be 'crop' or 'pad', got {self.edge_mode!r}")
        if self.compression not in _SUPPORTED_COMPRESSION:
            raise ValueError(
                f"compression must be one of {', '.join(repr(c) for c in _SUPPORTED_COMPRESSION)}, got {self.compression!r}"
            )


def _paths_refer_to_same_file(input_path: Path, output_path: Path) -> bool:
    """Return True when two paths would target the same filesystem object."""
    try:
        return input_path.samefile(output_path)
    except (FileNotFoundError, OSError):
        pass

    return os.path.normcase(os.path.abspath(input_path)) == os.path.normcase(
        os.path.abspath(output_path)
    )
