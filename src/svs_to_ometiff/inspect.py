"""
SVS inspection helper and CLI command.

Provides a lightweight way to inspect source SVS metadata without decoding
any image tiles. Reuses ``read_svs_metadata`` from the tile_reader module.
"""

import sys

import click

from svs_to_ometiff.tile_reader import read_svs_metadata

SUPPORTED_COMPRESSION = 33007


def inspect_svs(path: str) -> dict[str, object]:
    """
    Return metadata about a source SVS file.

    Does not decode any image tiles — only reads TIFF headers and tags.

    Args:
        path: Path to the SVS file.

    Returns:
        Dict with keys: compression, width, height, convertible,
        src_tile_width, src_tile_height, tile_count, mpp.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: Propagated from ``read_svs_metadata`` on invalid SVS.
    """
    meta = read_svs_metadata(path)
    compression = meta["compression"]
    return {
        "compression": compression,
        "width": meta["width"],
        "height": meta["height"],
        "convertible": compression == SUPPORTED_COMPRESSION,
        "src_tile_width": meta["src_tile_width"],
        "src_tile_height": meta["src_tile_height"],
        "tile_count": meta["tile_count"],
        "mpp": meta["mpp"],
    }


@click.command()
@click.argument("svs_path", type=click.Path(exists=True))
def main(svs_path: str) -> None:
    """Inspect a source SVS file and print its metadata."""
    try:
        info = inspect_svs(svs_path)
    except FileNotFoundError:
        click.echo(f"Error: file not found: {svs_path}", err=True)
        sys.exit(1)
    except (ValueError, Exception) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not info["convertible"]:
        click.echo(
            f"Error: unsupported compression {info['compression']} "
            f"(only {SUPPORTED_COMPRESSION} is convertible)",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Compression: {info['compression']}")
    click.echo(f"Dimensions: {info['width']} x {info['height']}")
    click.echo(f"Tile size: {info['src_tile_width']} x {info['src_tile_height']}")
    mpp = info["mpp"]
    click.echo(f"MPP: {mpp}")
    click.echo("Convertible: yes")
