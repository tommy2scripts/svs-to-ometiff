"""Configuration objects for svs-to-ometiff conversion."""

from dataclasses import dataclass, fields
from typing import Any, Literal, Optional

from svs_to_ometiff.utils import ProgressLogger

_SUPPORTED_COMPRESSION = (None, "lzw", "zlib", "deflate")


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

    def __post_init__(self) -> None:
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
        """
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def _validate(self) -> None:
        if self.tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if self.tile_size % 16 != 0:
            raise ValueError("tile_size must be divisible by 16")
        if self.num_levels < 1:
            raise ValueError("num_levels must be at least 1")
        if self.downsample_factor < 2:
            raise ValueError("downsample_factor must be at least 2")
        if self.compression not in _SUPPORTED_COMPRESSION:
            if self.compression == "jpeg2000":
                raise ValueError(
                    "compression='jpeg2000' is not supported by svs-to-ometiff. "
                    "Use 'zlib', 'lzw', 'deflate', or None/'none'; "
                    "recompress the output separately if JPEG 2000 is required."
                )
            raise ValueError(
                f"compression must be one of {', '.join(repr(c) for c in _SUPPORTED_COMPRESSION)}, got {self.compression!r}"
            )
