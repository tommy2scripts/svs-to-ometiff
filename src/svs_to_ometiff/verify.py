"""
OME-TIFF verification helper and CLI command.

Validates that a TIFF file conforms to expected OME BigTIFF pyramidal
structure using tifffile.
"""

import sys

import click
import tifffile


def verify_ometiff(path: str, *, min_levels: int = 1) -> dict:
    """Validate OME BigTIFF structure of *path*.

    Checks:
    - ``tif.is_ome`` is True
    - ``tif.is_bigtiff`` is True
    - ``tif.series`` exists and has at least *min_levels*
    - Each level has RGB shape (Y, X, 3)
    - Level 0 dtype is uint8

    Args:
        path: Path to the TIFF file.
        min_levels: Minimum number of pyramid levels required.

    Returns:
        dict with keys ``is_ome``, ``is_bigtiff``, ``levels``, ``subifds``,
        ``dtype``, and ``pass``.
    """
    errors: list[str] = []

    with tifffile.TiffFile(path) as tif:
        is_ome = tif.is_ome
        is_bigtiff = tif.is_bigtiff

        if not is_ome:
            errors.append("Not an OME-TIFF (is_ome=False)")
        if not is_bigtiff:
            errors.append("Not a BigTIFF (is_bigtiff=False)")

        # Check series and levels
        if not tif.series:
            errors.append("No series found in TIFF")
            return {
                "is_ome": is_ome,
                "is_bigtiff": is_bigtiff,
                "levels": [],
                "subifds": 0,
                "dtype": None,
                "pass": False,
                "errors": errors,
            }

        series = tif.series[0]
        levels = series.levels
        level_shapes = [lvl.shape for lvl in levels]

        if len(levels) < min_levels:
            errors.append(
                f"Expected at least {min_levels} levels, found {len(levels)}"
            )

        # Check RGB shape for each level
        for i, lvl in enumerate(levels):
            if len(lvl.shape) != 3 or lvl.shape[2] != 3:
                errors.append(
                    f"Level {i} is not RGB (Y, X, 3), got shape {lvl.shape}"
                )

        # Check level 0 dtype
        dtype = None
        if levels:
            dtype = str(levels[0].dtype)
            if dtype != "uint8":
                errors.append(f"Level 0 dtype is {dtype}, expected uint8")

        # SubIFD info
        subifds = len(levels) - 1 if len(levels) > 1 else 0

        passed = len(errors) == 0

        return {
            "is_ome": is_ome,
            "is_bigtiff": is_bigtiff,
            "levels": level_shapes,
            "subifds": subifds,
            "dtype": dtype,
            "pass": passed,
            "errors": errors,
        }


@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--min-levels",
    default=1,
    type=int,
    show_default=True,
    help="Minimum number of pyramid levels required.",
)
def main(path: str, min_levels: int) -> None:
    """Verify an OME-TIFF file's structure.

    PATH is the path to the OME-TIFF file to verify.

    Exit code 0 means all checks passed, exit code 1 means one or more
    checks failed.
    """
    try:
        result = verify_ometiff(path, min_levels=min_levels)
    except Exception as exc:
        click.echo(f"[FAIL] {path}")
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    status = "PASS" if result["pass"] else "FAIL"
    click.echo(f"[{status}] {path}")
    click.echo(f"OME: {'yes' if result['is_ome'] else 'no'}")
    click.echo(f"BigTIFF: {'yes' if result['is_bigtiff'] else 'no'}")
    click.echo(f"Levels: {len(result['levels'])}")
    click.echo(f"Level shapes: {result['levels']}")
    click.echo(f"Dtype: {result['dtype']}")

    if result["errors"]:
        for err in result["errors"]:
            click.echo(f"  - {err}", err=True)

    if not result["pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
