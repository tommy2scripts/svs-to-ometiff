"""Configuration objects for svs-to-ometiff conversion."""

from dataclasses import dataclass
from typing import Literal, Optional

from svs_to_ometiff.utils import ProgressLogger

_SUPPORTED_COMPRESSION = (None, "lzw", "zlib", "deflate")


@dataclass(frozen=True)
class ConvertConfig:
    """Inputs and options for :func:`svs_to_ometiff.converter.convert`."""

    input_svs: str
    output_ometiff: str
    tile_size: int = 512
    compression: Optional[str] = None
    num_levels: int = 3
    downsample_factor: int = 2
    edge_mode: Literal["crop", "pad"] = "crop"
    image_name: Optional[str] = None
    verbose: bool = True
    tile_progress_interval: int = 20
    progress_logger: Optional[ProgressLogger] = None

    def __post_init__(self) -> None:
        self._validate()

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
                    "compression='jpeg2000' is not supported by svs-to-ometiff "
                    "this release. Use 'zlib', 'lzw', 'deflate', or None/'none'; "
                    "recompress the output separately if JPEG 2000 is required."
                )
            raise ValueError(
                f"compression must be one of {', '.join(repr(c) for c in _SUPPORTED_COMPRESSION)}, got {self.compression!r}"
            )
