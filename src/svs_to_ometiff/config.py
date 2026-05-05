"""Configuration objects for svs-to-ometiff conversion."""

from dataclasses import dataclass
from typing import Literal, Optional

from svs_to_ometiff.utils import ProgressLogger


@dataclass(frozen=True)
class ConvertConfig:
    """Inputs and options for :func:`svs_to_ometiff.converter.convert`."""

    input_svs: str
    output_ometiff: str
    tile_size: int = 512
    compression: Optional[str] = "lzw"
    num_levels: int = 6
    downsample_factor: int = 2
    edge_mode: Literal["crop", "pad"] = "crop"
    image_name: Optional[str] = None
    verbose: bool = True
    tile_progress_interval: int = 20
    progress_logger: Optional[ProgressLogger] = None
