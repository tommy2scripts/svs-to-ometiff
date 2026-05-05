"""
svs_to_ometiff — Convert Aperio SVS (compression 33007) to pyramidal OME-TIFF.

Handles the observed proprietary YUYV raw YCbCr 4:2:2 format used by some
Aperio AT2/GT450 exports. This payload is not standard JPEG or JPEG 2000
and may not decode in Bio-Formats, OpenSlide, or standard tifffile paths.

Modules:
    yuyv_decoder  — YUYV (YCbCr 4:2:2) → RGB using BT.601 full-range
    tile_reader   — Read and reassemble SVS tiles into full-resolution image
    pyramid       — Build multi-resolution pyramid by block averaging
    writer        — Write pyramidal OME-TIFF with SubIFD linkage
    cli           — Click-based command-line interface
"""

__version__ = "0.2.0"
__all__ = [
    "yuyv_to_rgb",
    "read_svs_full_image",
    "parse_mpp_from_description",
    "build_pyramid",
    "write_pyramidal_ometiff",
    "build_ome_xml",
    "convert",
    "estimate_peak_ram_bytes",
]

from svs_to_ometiff.yuyv_decoder import yuyv_to_rgb
from svs_to_ometiff.tile_reader import parse_mpp_from_description, read_svs_full_image
from svs_to_ometiff.pyramid import build_pyramid
from svs_to_ometiff.writer import write_pyramidal_ometiff, build_ome_xml
from svs_to_ometiff.converter import convert, estimate_peak_ram_bytes
