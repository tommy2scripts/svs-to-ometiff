"""
Batch conversion CLI for svs-to-ometiff.

Converts all Aperio SVS files matching a glob pattern or in a directory
to pyramidal OME-TIFF. Each file is processed independently; failures
on one file do not stop the rest.
"""

import glob
import sys
import time
from pathlib import Path
from typing import Optional

import click

from svs_to_ometiff import __version__
from svs_to_ometiff.converter import convert


@click.command()
@click.argument("input_pattern", type=str)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Output directory for converted files (default: same directory as input).",
)
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
    type=click.Choice(["zlib", "lzw", "deflate", "none"]),
    show_default=True,
    help="TIFF compression scheme. Use 'none' for maximum compatibility.",
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
    "--temp-dir",
    type=click.Path(),
    default=None,
    help="Directory for temporary staging files (use a local SSD when reading/writing over network shares).",
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
@click.version_option(version=__version__, prog_name="svs-to-ometiff-batch")
def main(
    input_pattern: str,
    output_dir: Optional[str],
    tile_size: int,
    compression: str,
    num_levels: int,
    downsample_factor: int,
    edge_mode: str,
    temp_dir: Optional[str],
    quiet: bool,
    verbose: bool,
) -> None:
    """
    Batch-convert Aperio SVS files to pyramidal OME-TIFF.

    INPUT_PATTERN is a glob pattern (e.g. '*.svs', 'slides/*.svs') or a
    directory path. If a directory is given, all *.svs files in it are
    converted.

    Each output file is written alongside its input file as
    <stem>.ome.tiff, or into --output-dir if specified.

    \b
    Examples:
        svs-to-ometiff-batch '*.svs'
        svs-to-ometiff-batch slides/ --output-dir converted/
        svs-to-ometiff-batch '/data/**/*.svs' --compression lzw
        svs-to-ometiff-batch '/mnt/nas/slides/**/*.svs' --output-dir /mnt/nas/converted \
            --temp-dir /local_nvme/svs_tmp
    """
    show_progress = verbose or not quiet

    # Resolve input files
    if Path(input_pattern).is_dir():
        files = sorted(glob.glob(str(Path(input_pattern) / "*.svs")))
    else:
        files = sorted(glob.glob(input_pattern, recursive=True))

    if not files:
        click.echo(f"No SVS files matched: {input_pattern}", err=True)
        sys.exit(1)

    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    compression_arg: Optional[str] = None if compression == "none" else compression
    tile_progress_interval = 1 if verbose else 20

    click.echo(f"svs-to-ometiff-batch v{__version__}")
    click.echo(f"Found {len(files)} SVS file(s) to convert")
    click.echo()

    succeeded = 0
    failed = 0
    t_total = time.time()

    for i, svs_path in enumerate(files, start=1):
        stem = Path(svs_path).stem
        if output_dir is not None:
            out_path = str(Path(output_dir) / f"{stem}.ome.tiff")
        else:
            out_path = str(Path(svs_path).parent / f"{stem}.ome.tiff")

        click.echo(f"[{i}/{len(files)}] {svs_path} -> {out_path}")

        try:
            convert(
                svs_path,
                out_path,
                tile_size=tile_size,
                compression=compression_arg,
                num_levels=num_levels,
                downsample_factor=downsample_factor,
                edge_mode=edge_mode,
                temp_dir=temp_dir,
                verbose=show_progress,
                tile_progress_interval=tile_progress_interval,
            )
            succeeded += 1
        except Exception as exc:
            click.echo(f"  ERROR: {exc}", err=True)
            failed += 1

        click.echo()

    elapsed = time.time() - t_total
    click.echo(f"Batch complete: {succeeded} succeeded, {failed} failed in {elapsed:.0f}s")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
