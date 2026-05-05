"""
Command-line interface for svs-to-ometiff.

Converts Aperio SVS files with compression 33007 (YUYV raw YCbCr 4:2:2)
to pyramidal OME-TIFF with SubIFD linkage.
"""

import sys
from typing import Optional

import click

from svs_to_ometiff.converter import convert


def _print_experimental_warning() -> None:
    """Print a prominent experimental-status warning to stderr."""
    import sys
    sys.stderr.write(
        "⚠️  svs-to-ometiff v0.2.0 — EXPERIMENTAL\n"
        "   Validated on 1 file (AT2/GT450, lung H&E, compression 33007).\n"
        "   Output has NOT been validated for diagnostic use.\n"
        "   Please verify results independently before any clinical or research use.\n"
        "   See README.md for full validation status.\n"
    )


@click.command()
@click.argument("input_svs", type=click.Path(exists=True))
@click.argument("output_ometiff", type=click.Path())
@click.option(
    "--tile-size",
    default=512,
    type=int,
    show_default=True,
    help="Output tile size (square) for the OME-TIFF.",
)
@click.option(
    "--compression",
    default="lzw",
    type=click.Choice(["lzw", "zlib", "deflate", "none"]),
    show_default=True,
    help="TIFF compression scheme. Use 'lzw' for lossless.",
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
@click.version_option(version="0.2.0", prog_name="svs-to-ometiff")
def main(
    input_svs: str,
    output_ometiff: str,
    tile_size: int,
    compression: str,
    num_levels: int,
    downsample_factor: int,
    edge_mode: str,
    image_name: Optional[str],
    quiet: bool,
    verbose: bool,
) -> None:
    """
    Convert an Aperio SVS file to pyramidal OME-TIFF.

    INPUT_SVS is the path to the source .svs file (Aperio compression 33007).

    OUTPUT_OMETIFF is the destination path for the .ome.tiff file.

    This tool handles Aperio compression 33007 (raw YUYV YCbCr 4:2:2)
    which may not be supported by Bio-Formats, OpenSlide, or standard
    tifffile decoding paths. It uses a custom BT.601 YCbCr-to-RGB decoder.

    Example:

        svs-to-ometiff slide.svs slide.ome.tiff --tile-size 512 --compression lzw
    """
    show_progress = verbose or not quiet
    tile_progress_interval = 1 if verbose else 20

    # Experimental warning
    _print_experimental_warning()

    # Compression 'none' means no compression
    compression_arg: Optional[str] = None if compression == "none" else compression

    try:
        convert(
            input_svs,
            output_ometiff,
            tile_size=tile_size,
            compression=compression_arg,
            num_levels=num_levels,
            downsample_factor=downsample_factor,
            edge_mode=edge_mode,
            image_name=image_name,
            verbose=show_progress,
            tile_progress_interval=tile_progress_interval,
        )
    except Exception as exc:
        click.echo(f"Error converting SVS file: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
