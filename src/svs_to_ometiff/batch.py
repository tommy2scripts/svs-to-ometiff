"""
Batch conversion CLI for svs-to-ometiff.

Converts all Aperio SVS files matching a glob pattern or in a directory
to pyramidal OME-TIFF. Each file is processed independently; failures
on one file do not stop the rest.
"""

import glob
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

import click

from svs_to_ometiff import __version__
from svs_to_ometiff.batch_plan import (
    find_duplicate_output_paths,
    output_path_for_input,
)
from svs_to_ometiff.batch_manifest import (
    BatchManifestRecord,
    utc_now_iso,
    write_json_manifest,
)
from svs_to_ometiff.converter import convert
from svs_to_ometiff.verify import verify_ometiff


class OutputExistsError(RuntimeError):
    """Raised when a batch output exists and overwrite was not requested."""


def _parse_json_dict(
    _ctx: click.Context,
    _param: click.Parameter,
    value: Optional[str],
) -> Optional[dict[str, Any]]:
    """Parse a JSON string into a dict for --compression-args."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.BadParameter("must be a JSON object, e.g. '{\"level\":80}'")
    return parsed


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
@click.option(
    "--skip-existing",
    is_flag=True,
    help="Skip files whose planned output already exists.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Allow overwriting existing output files.",
)
@click.option(
    "--manifest",
    default=None,
    type=click.Path(),
    help="Write a JSON batch manifest with per-file statuses.",
)
@click.option(
    "--verify",
    is_flag=True,
    help="Run svs-to-ometiff-verify after each successful conversion.",
)
@click.option(
    "--verify-existing",
    is_flag=True,
    help="With --skip-existing and --verify, verify skipped existing outputs.",
)
@click.option(
    "--continue-on-error",
    is_flag=True,
    help="Continue processing remaining files after a failed file.",
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Stop at the first failed file.",
)
@click.version_option(version=__version__, prog_name="svs-to-ometiff-batch")
def main(
    input_pattern: str,
    output_dir: Optional[str],
    tile_size: int,
    compression: str,
    compression_args: Optional[dict[str, Any]],
    num_levels: int,
    downsample_factor: int,
    edge_mode: str,
    quiet: bool,
    verbose: bool,
    temp_dir: Optional[str],
    skip_existing: bool,
    force: bool,
    manifest: Optional[str],
    verify: bool,
    verify_existing: bool,
    continue_on_error: bool,
    fail_fast: bool,
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
    if continue_on_error and fail_fast:
        raise click.UsageError("--continue-on-error and --fail-fast are mutually exclusive")
    if skip_existing and force:
        raise click.UsageError("--skip-existing and --force are mutually exclusive")
    if verify_existing and not skip_existing:
        raise click.UsageError("--verify-existing requires --skip-existing")

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

    duplicate_outputs = find_duplicate_output_paths(files, output_dir)
    if duplicate_outputs:
        click.echo("Batch output path collision detected:", err=True)
        for out_path, input_paths in duplicate_outputs.items():
            click.echo(f"  {out_path}", err=True)
            for input_path in input_paths:
                click.echo(f"    - {input_path}", err=True)
        click.echo(
            "Use distinct filenames or split the batch to avoid overwriting outputs.",
            err=True,
        )
        sys.exit(1)

    compression_arg: Optional[str] = None if compression == "none" else compression
    tile_progress_interval = 1 if verbose else 20

    click.echo(f"svs-to-ometiff-batch v{__version__}")
    click.echo(f"Found {len(files)} SVS file(s) to convert")
    click.echo()

    succeeded = 0
    skipped = 0
    failed = 0
    t_total = time.time()
    records: list[BatchManifestRecord] = []

    def save_manifest() -> None:
        if manifest is not None:
            write_json_manifest(manifest, records)

    for i, svs_path in enumerate(files, start=1):
        out_path = output_path_for_input(svs_path, output_dir)
        record = BatchManifestRecord(
            input_path=str(svs_path),
            output_path=str(out_path),
            start_time=utc_now_iso(),
        )
        records.append(record)

        click.echo(f"[{i}/{len(files)}] {svs_path} -> {out_path}")

        try:
            if Path(out_path).exists() and not force:
                if skip_existing:
                    record.output_size_bytes = Path(out_path).stat().st_size
                    record.output_size_gb = record.output_size_bytes / 1e9
                    if verify and verify_existing:
                        verification = verify_ometiff(
                            out_path,
                            min_levels=num_levels,
                            expected_tile_size=tile_size,
                        )
                        record.update_from_verification(verification)
                    record.finish("skipped_existing")
                    skipped += 1
                    click.echo("  skipped: output already exists")
                    save_manifest()
                    click.echo()
                    continue
                raise OutputExistsError(
                    f"Output already exists: {out_path}. Use --skip-existing "
                    "to leave it unchanged or --force to overwrite it."
                )

            result = convert(
                svs_path,
                out_path,
                tile_size=tile_size,
                compression=compression_arg,
                compressionargs=compression_args,
                num_levels=num_levels,
                downsample_factor=downsample_factor,
                edge_mode=edge_mode,
                verbose=show_progress,
                tile_progress_interval=tile_progress_interval,
                temp_dir=temp_dir,
            )
            record.update_from_conversion_result(result)
            status = "converted"
            if verify:
                verification = verify_ometiff(
                    out_path,
                    min_levels=num_levels,
                    expected_tile_size=tile_size,
                )
                record.update_from_verification(verification)
                if not record.verify_pass:
                    status = "verify_failed"
                    failed += 1
                else:
                    succeeded += 1
            else:
                succeeded += 1
            record.finish(status)
        except Exception as exc:
            click.echo(f"  ERROR: {exc}", err=True)
            record.update_from_exception(exc)
            record.finish("failed")
            failed += 1
            save_manifest()
            if fail_fast:
                click.echo()
                break
        else:
            save_manifest()

        click.echo()

    elapsed = time.time() - t_total
    click.echo(
        f"Batch complete: {succeeded} succeeded, {skipped} skipped, "
        f"{failed} failed in {elapsed:.0f}s"
    )
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
