"""
OME-TIFF verification helper and CLI command.

Validates that a TIFF file conforms to expected OME BigTIFF pyramidal
structure using tifffile.
"""

import sys
import xml.etree.ElementTree as ET
from typing import Optional

import click
import tifffile


def _extract_physical_pixel_sizes(
    ome_xml: Optional[str],
) -> tuple[Optional[float], Optional[float]]:
    if not ome_xml:
        return None, None
    try:
        root = ET.fromstring(ome_xml)
    except ET.ParseError:
        return None, None

    pixels = None
    for elem in root.iter():
        if elem.tag.endswith("Pixels"):
            pixels = elem
            break
    if pixels is None:
        return None, None

    def _get_float(name: str) -> Optional[float]:
        value = pixels.attrib.get(name)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    return _get_float("PhysicalSizeX"), _get_float("PhysicalSizeY")


def verify_ometiff(
    path: str,
    *,
    min_levels: int = 1,
    expected_tile_size: Optional[int] = 1024,
) -> dict:
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
    warnings: list[str] = []

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
                "tile_width": None,
                "tile_height": None,
                "dtype": None,
                "physical_size_x": None,
                "physical_size_y": None,
                "pass": False,
                "errors": errors,
                "warnings": warnings,
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
        if len(levels) > 1 and subifds == 0:
            errors.append("No SubIFD pyramid levels found")

        page0 = tif.pages[0]
        tile_width = getattr(page0, "tilewidth", None)
        tile_height = getattr(page0, "tilelength", None)
        if tile_width is None and "TileWidth" in page0.tags:
            tile_width = int(page0.tags["TileWidth"].value)
        if tile_height is None and "TileLength" in page0.tags:
            tile_height = int(page0.tags["TileLength"].value)
        if tile_width is None or tile_height is None:
            errors.append("Level 0 is not tiled")
        elif expected_tile_size is not None and (
            tile_width != expected_tile_size or tile_height != expected_tile_size
        ):
            warnings.append(
                f"Level 0 tile size is {tile_width} x {tile_height}; expected "
                f"{expected_tile_size} x {expected_tile_size} for the default profile"
            )

        physical_size_x, physical_size_y = _extract_physical_pixel_sizes(
            tif.ome_metadata
        )
        if physical_size_x is None or physical_size_y is None:
            warnings.append("OME physical pixel size / MPP metadata was not found")

        passed = len(errors) == 0

        return {
            "is_ome": is_ome,
            "is_bigtiff": is_bigtiff,
            "levels": level_shapes,
            "subifds": subifds,
            "tile_width": tile_width,
            "tile_height": tile_height,
            "dtype": dtype,
            "physical_size_x": physical_size_x,
            "physical_size_y": physical_size_y,
            "pass": passed,
            "errors": errors,
            "warnings": warnings,
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
    click.echo(f"SubIFDs: {result['subifds']}")
    click.echo(f"Tile size: {result['tile_width']} x {result['tile_height']}")
    if result["physical_size_x"] is not None and result["physical_size_y"] is not None:
        click.echo(
            "Physical pixel size: "
            f"{result['physical_size_x']} x {result['physical_size_y']} µm/px"
        )
    else:
        click.echo("Physical pixel size: not found")

    if result["warnings"]:
        click.echo("Warnings:")
        for warning in result["warnings"]:
            click.echo(f"  - {warning}", err=True)

    if result["errors"]:
        click.echo("Errors:")
        for err in result["errors"]:
            click.echo(f"  - {err}", err=True)

    if not result["pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
