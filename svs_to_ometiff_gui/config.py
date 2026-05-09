"""Application configuration — externalized from hardcoded values.

Reads from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration, loaded from environment variables."""

    # Server
    HOST: str = os.environ.get("SVS_GUI_HOST", "127.0.0.1")
    PORT: int = int(os.environ.get("SVS_GUI_PORT", "8765"))

    # Conversion defaults
    DEFAULT_TILE_SIZE: int = int(os.environ.get("SVS_GUI_TILE_SIZE", "1024"))
    DEFAULT_COMPRESSION: str = os.environ.get("SVS_GUI_COMPRESSION", "zlib")
    DEFAULT_NUM_LEVELS: int = int(os.environ.get("SVS_GUI_NUM_LEVELS", "6"))
    DEFAULT_DOWNSAMPLE: int = int(os.environ.get("SVS_GUI_DOWNSAMPLE", "2"))
    DEFAULT_EDGE_MODE: str = os.environ.get("SVS_GUI_EDGE_MODE", "crop")

    # Limits
    MAX_CONCURRENT_JOBS: int = int(os.environ.get("SVS_GUI_MAX_JOBS", "1"))

    def __post_init__(self):
        if self.HOST == "0.0.0.0":
            import logging
            logging.getLogger("svs_to_ometiff_gui").warning(
                "⚠ Server bound to all interfaces (0.0.0.0). "
                "This exposes your filesystem to the network."
            )
