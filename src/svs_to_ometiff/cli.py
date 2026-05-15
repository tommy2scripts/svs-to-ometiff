"""
Command-line interface for svs-to-ometiff.

Converts Aperio SVS files with compression 33007 (YUYV raw YCbCr 4:2:2)
to pyramidal OME-TIFF with SubIFD linkage.
"""

import json
import sys
from typing import Any, Optional

import click

from svs_to_ometiff import __version__
from svs_to_ometiff.converter import convert


def _print_experimental_warning() -> None:
    """Print a prominent experimental-status warning to stderr."""
    sys.stderr.write(
        f"WARNING  svs-to-ometiff v{__version__} - EXPERIMENTAL\n"
        "   Validated on 1 file (AT2/GT450, lung H&E, compression 33007).\n"
        "   Output has NOT been validated for diagnostic use.\n"
        "   Please verify results independently before any clinical or research use.\n"
        "   See README.md for full validation status.\n"
    )


def _parse_json_dict(_ctx: click.Context, _param: click.Parameter,
                     value: Optional[str]) -> Optional[dict[str, Any]]:
    """Parse a JSON string into a dict for --compression-args."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid JSON: {exc}")
    if not isinstance(parsed, dict):
        raise click.BadParameter("must be a JSON object, e.g. '{\"level\":80}'")
    return parsed


@click.command()
@click.argument("input_svs", type=click.Path(exists=True))
@click.argument("output_ometiff", type=click.Path())
@click.option(
    "--tile-size",
    default=1024,
    type=int,
    show_default=True,
    help="Output tile size (square) for the OME-TIFF.",
)
@click.option(
    "--compression",
    default="zlib",
    type=click.Choice(["zlib", "lzw", "deflate", "jpeg", "jpeg2000", "none"]),
    show_default=True,
    help="TIFF compression scheme. 'jpeg' is lossy; 'jpeg2000' requires "
         "imagecodecs[jpeg2k]. Use 'none' for maximum compatibility.",
)
@click.option(
    "--compression-args",
    default=None,
    type=str,
    callback=_parse_json_dict,
    help="JSON dict of codec-specific arguments, e.g. '{\"level\":80}' for JPEG.",
)
@click.option(
    "--num-levels",
    default=6,
    type=int,
    show_default=True,
    help="Number of pyramid levels (including full resolution).",
)
@click.option(
    "--downsample-factor",
    default=2,
    type=int,
    show_default=True,
    help="Downsampling factor between pyramid levels.",
)
@click.option(
    "--edge-mode",
    default="crop",
    type=click.Choice(["crop", "pad"]),
    show_default=True,
    help="Border behavior when dimensions are not divisible by downsample factor.",
)
@click.option(
    "--image-name",
    default=None,
    type=str,
    help="Name for the OME Image element (default: derived from input filename).",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Suppress progress output.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print detailed progress, including every source tile row.",
)
@click.option(
    "--temp-dir",
    default=None,
    type=click.Path(),
    help="Directory for temporary files (default: system temp dir). "
         "Use a local drive on Windows to avoid network-locking issues.",
)
@click.version_option(version=__version__, prog_name="svs-to-ometiff")
def main(
    input_svs: str,
    output_ometiff: str,
    tile_size: int,
    compression: str,
    compression_args: Optional[dict[str, Any]],
    num_levels: int,
    downsample_factor: int,
    edge_mode: str,
    image_name: Optional[str],
    quiet: bool,
    verbose: bool,
    temp_dir: Optional[str],
) -> None:
    """
    Convert an Aperio SVS file to pyramidal OME-TIFF.

    INPUT_SVS is the path to the source .svs file (Aperio compression 33007).

    OUTPUT_OMETIFF is the destination path for the .ome.tiff file.

    This tool handles Aperio compression 33007 (raw YUYV YCbCr 4:2:2)
    which may not be supported by Bio-Formats, OpenSlide, or standard
    tifffile decoding paths. It uses a custom BT.601 YCbCr-to-RGB decoder.

    Example:

        svs-to-ometiff slide.svs slide.ome.tiff --tile-size 1024 --compression zlib
        svs-to-ometiff \\
            /mnt/nas/slides/slide.svs /mnt/nas/out/slide.ome.tiff \\
            --temp-dir /local_nvme/svs_tmp
    """
    show_progress = verbose or not quiet
    tile_progress_interval = 1 if verbose else 20

    # Experimental warning
    _print_experimental_warning()

    try:
        convert(
            input_svs,
            output_ometiff,
            tile_size=tile_size,
            compression=compression,
            compressionargs=compression_args,
            num_levels=num_levels,
            downsample_factor=downsample_factor,
            edge_mode=edge_mode,
            image_name=image_name,
            verbose=show_progress,
            tile_progress_interval=tile_progress_interval,
            temp_dir=temp_dir,
        )
    except Exception as exc:
        click.echo(f"Error: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
