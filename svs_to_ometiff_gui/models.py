"""Domain models for svs-to-ometiff GUI.

Replaces raw dictionaries with typed dataclasses for conversion jobs
and slide metadata, improving code clarity and enabling validation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversionJob:
    """Represents a single SVS → OME-TIFF conversion request."""

    input_path: str
    output_path: str = ""
    tile_size: int = 1024
    compression: Optional[str] = "zlib"
    num_levels: int = 6
    downsample_factor: int = 2
    edge_mode: str = "crop"
    temp_dir: Optional[str] = None
    request_id: str = ""

    def to_converter_kwargs(self) -> dict:
        """
        Builds a keyword-arguments dictionary for calling the converter's `convert()` function.
        
        The returned dict maps converter parameter names to this job's fields. Empty `output_path` is returned as `None`, `compression` is returned as `None` when set to `"none"`, and `temp_dir` is returned as `None` when unset.
        
        Returns:
            dict: A mapping with keys:
                - "config_or_input_svs": input path string
                - "output_ometiff": output path string or `None`
                - "tile_size": tile size integer
                - "compression": compression string or `None`
                - "num_levels": number of pyramid levels integer
                - "downsample_factor": downsample factor integer
                - "edge_mode": edge handling string
                - "temp_dir": temporary directory path string or `None`
        """
        return {
            "config_or_input_svs": self.input_path,
            "output_ometiff": self.output_path or None,
            "tile_size": self.tile_size,
            "compression": self.compression if self.compression != "none" else None,
            "num_levels": self.num_levels,
            "downsample_factor": self.downsample_factor,
            "edge_mode": self.edge_mode,
            "temp_dir": self.temp_dir or None,
        }


@dataclass
class SlideMetadata:
    """Metadata extracted from an SVS file via ``inspect_svs``."""

    width: int = 0
    height: int = 0
    mpp: Optional[float] = None
    magnification: Optional[float] = None
    compression: str = ""
    src_tile_width: int = 0
    src_tile_height: int = 0
    tile_count: int = 0
    convertible: bool = False
    resolved_path: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SlideMetadata":
        """Build a SlideMetadata from a raw dict (e.g. inspect_svs result)."""
        return cls(
            width=data.get("width", 0),
            height=data.get("height", 0),
            mpp=data.get("mpp"),
            magnification=data.get("magnification"),
            compression=data.get("compression", ""),
            src_tile_width=data.get("src_tile_width", 0),
            src_tile_height=data.get("src_tile_height", 0),
            tile_count=data.get("tile_count", 0),
            convertible=data.get("convertible", False),
            resolved_path=data.get("resolved_path", ""),
        )
