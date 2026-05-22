"""Domain models for svs-to-ometiff GUI.

Replaces raw dictionaries with typed dataclasses for conversion jobs
and slide metadata, improving code clarity and enabling validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Optional

if TYPE_CHECKING:
    from svs_to_ometiff.config import ConvertConfig


@dataclass
class ConversionJob:
    """Represents a single SVS → OME-TIFF conversion request."""

    input_path: str
    output_path: str = ""
    tile_size: int = 1024
    compression: Optional[str] = "zlib"
    num_levels: int = 6
    downsample_factor: int = 2
    edge_mode: Literal["crop", "pad"] = "crop"
    temp_dir: Optional[str] = None
    request_id: str = ""
    compressionargs: Optional[dict[str, Any]] = None

    def to_convert_config(self) -> "ConvertConfig":
        """Return the authoritative core conversion configuration for this job."""
        from svs_to_ometiff.config import ConvertConfig

        return ConvertConfig(
            input_svs=self.input_path,
            output_ometiff=self.output_path or "",
            tile_size=self.tile_size,
            compression=self.compression,
            num_levels=self.num_levels,
            downsample_factor=self.downsample_factor,
            edge_mode=self.edge_mode,
            temp_dir=self.temp_dir,
            compressionargs=self.compressionargs,
        )

    @classmethod
    def from_convert_config(
        cls,
        config: "ConvertConfig",
        *,
        request_id: str = "",
    ) -> "ConversionJob":
        """Build a GUI job from a normalized core conversion configuration."""
        compression = "none" if config.compression is None else config.compression
        return cls(
            input_path=config.input_svs,
            output_path=config.output_ometiff,
            tile_size=config.tile_size,
            compression=compression,
            num_levels=config.num_levels,
            downsample_factor=config.downsample_factor,
            edge_mode=config.edge_mode,
            temp_dir=config.temp_dir,
            request_id=request_id,
            compressionargs=config.compressionargs,
        )

    def to_converter_kwargs(self) -> dict:
        """Return pickle-safe kwargs suitable for passing to ``convert()``.

        Conversion option validation and normalization are delegated to
        :class:`ConvertConfig`; this method is only the GUI worker Adapter that
        preserves the current public ``convert`` call shape.
        """
        config = self.to_convert_config()
        d = config.to_dict()
        d["config_or_input_svs"] = d.pop("input_svs")
        if not self.output_path:
            d["output_ometiff"] = None
        return d


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
