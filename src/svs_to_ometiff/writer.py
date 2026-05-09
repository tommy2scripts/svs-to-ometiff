"""
OME-TIFF writer with SubIFD pyramid linkage.

Writes a multi-resolution pyramidal OME-TIFF using tifffile's TiffWriter
with SubIFD structure. The subifds parameter on the full-resolution IFD
declares the sub-resolution levels, enabling pyramid detection in readers
that support SubIFD-linked pyramids.
"""

import os
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import quoteattr

import numpy as np
import tifffile

from svs_to_ometiff.utils import ProgressLogger, _log


def build_ome_xml(
    full_width: int,
    full_height: int,
    mpp: float,
    image_name: str = "Image",
    magnification: Optional[float] = None,
) -> str:
    """
    Build OME-XML metadata string for embedding in the TIFF description tag.

    Uses 7-bit ASCII-compatible characters only (``um`` not ``µm``).

    Args:
        full_width: Image width in pixels at full resolution.
        full_height: Image height in pixels at full resolution.
        mpp: Microns per pixel.
        image_name: Name for the OME Image element.
        magnification: Optional objective magnification (e.g. 20 or 40).
            When provided, ``<Instrument>`` and ``<Objective>`` elements are
            included in the OME-XML with ``NominalMagnification``.

    Returns:
        OME-XML string.
    """
    if full_width <= 0 or full_height <= 0:
        raise ValueError(
            f"OME image dimensions must be positive, got {full_width}x{full_height}"
        )
    if mpp <= 0:
        raise ValueError(f"mpp must be positive, got {mpp}")

    image_name_attr = quoteattr(image_name)

    # Build optional Instrument block when magnification is available
    instrument_block = ""
    image_instrument_refs = ""
    if magnification is not None and magnification > 0:
        mag_int = int(magnification) if magnification == int(magnification) else magnification
        instrument_block = (
            '  <Instrument ID="Instrument:0">\n'
            f'    <Objective ID="Objective:0" NominalMagnification="{mag_int}"/>\n'
            '  </Instrument>\n'
        )
        image_instrument_refs = (
            '    <InstrumentRef ID="Instrument:0"/>\n'
            '    <ObjectiveSettings ID="Objective:0"/>\n'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"\n'
        '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '     xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06'
        ' http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">\n'
        f"{instrument_block}"
        f"  <Image ID=\"Image:0\" Name={image_name_attr}>\n"
        f"{image_instrument_refs}"
        '    <Pixels ID="Pixels:0"\n'
        '            DimensionOrder="XYZCT"\n'
        '            Type="uint8"\n'
        f'            SizeX="{full_width}"\n'
        f'            SizeY="{full_height}"\n'
        '            SizeZ="1"\n'
        '            SizeC="3"\n'
        '            SizeT="1"\n'
        f'            PhysicalSizeX="{mpp}"\n'
        '            PhysicalSizeXUnit="um"\n'
        f'            PhysicalSizeY="{mpp}"\n'
        '            PhysicalSizeYUnit="um"\n'
        '            Interleaved="true">\n'
        '      <Channel ID="Channel:0:0" SamplesPerPixel="3"/>\n'
        '      <TiffData IFD="0" PlaneCount="1"/>\n'
        '    </Pixels>\n'
        '  </Image>\n'
        '</OME>'
    )


def _validate_rgb_level(level: np.ndarray, index: int) -> None:
    if level.ndim != 3 or level.shape[2] != 3:
        raise ValueError(f"Pyramid level {index} must be (H, W, 3), got {level.shape}")
    if level.dtype != np.uint8:
        raise ValueError(f"Pyramid level {index} must be uint8, got {level.dtype}")
    if level.shape[0] <= 0 or level.shape[1] <= 0:
        raise ValueError(f"Pyramid level {index} has empty dimensions: {level.shape}")


def _iter_padded_tiles(level: np.ndarray, tile_size: int):
    """Yield row-major square TIFF tiles, padding edge tiles to tile_size."""
    height, width = level.shape[:2]
    for y0 in range(0, height, tile_size):
        for x0 in range(0, width, tile_size):
            tile = level[y0 : y0 + tile_size, x0 : x0 + tile_size]
            if tile.shape[0] == tile_size and tile.shape[1] == tile_size:
                yield np.ascontiguousarray(tile)
                continue

            padded = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)
            padded[: tile.shape[0], : tile.shape[1]] = tile
            yield padded


def write_pyramidal_ometiff_from_levels(
    output_path: str,
    levels: Sequence[np.ndarray],
    mpp: float,
    *,
    tile_size: int = 512,
    compression: Optional[str] = "lzw",
    image_name: str = "Image",
    magnification: Optional[float] = None,
    verbose: bool = True,
    progress_logger: Optional[ProgressLogger] = None,
) -> None:
    """Write a pyramidal OME-TIFF from array-like levels via tile iterators."""
    if not levels:
        raise ValueError("levels must contain at least one level")
    if tile_size <= 0:
        raise ValueError(f"tile_size must be positive, got {tile_size}")
    if tile_size % 16 != 0:
        raise ValueError(
            f"tile_size must be divisible by 16 for tiled TIFF output, got {tile_size}"
        )
    if mpp <= 0:
        raise ValueError(f"mpp must be positive, got {mpp}")

    normalized_levels = [np.asarray(level) for level in levels]
    for index, level in enumerate(normalized_levels):
        _validate_rgb_level(level, index)

    full_img = normalized_levels[0]
    full_h, full_w = full_img.shape[:2]
    ome_xml = build_ome_xml(full_w, full_h, mpp, image_name, magnification=magnification)

    out_path = Path(output_path).resolve()
    output_dir = str(out_path.parent) or "."
    output_name = out_path.name
    temp_handle = tempfile.NamedTemporaryFile(
        prefix=f".{output_name}.",
        suffix=".tmp",
        dir=output_dir,
        delete=False,
    )
    temp_output_path = Path(temp_handle.name)
    temp_handle.close()

    _log(verbose, progress_logger, "Writing pyramidal OME-TIFF with SubIFD linkage...")
    _log(verbose, progress_logger, f"Levels: {[p.shape[:2] for p in normalized_levels]}")

    t0 = time.time()
    n_subifds = len(normalized_levels) - 1

    try:
        with tifffile.TiffWriter(str(temp_output_path), bigtiff=True) as tif:
            tif.write(
                _iter_padded_tiles(full_img, tile_size),
                shape=full_img.shape,
                dtype=full_img.dtype,
                description=ome_xml,
                subifds=n_subifds if n_subifds else None,
                tile=(tile_size, tile_size),
                compression=compression,
                photometric="rgb",
                metadata=None,
                resolution=(1e4 / mpp, 1e4 / mpp),
                resolutionunit=tifffile.RESUNIT.CENTIMETER,
            )
            _log(verbose, progress_logger, f"  Level 0: {full_w}x{full_h} written")

            for level_index, level in enumerate(normalized_levels[1:], start=1):
                tif.write(
                    _iter_padded_tiles(level, tile_size),
                    shape=level.shape,
                    dtype=level.dtype,
                    subfiletype=1,
                    tile=(tile_size, tile_size),
                    compression=compression,
                    photometric="rgb",
                    metadata=None,
                )
                _log(
                    verbose,
                    progress_logger,
                    f"  Level {level_index}: {level.shape[1]}x{level.shape[0]} written",
                )

        temp_output_path.replace(output_path)
    except Exception:
        if temp_output_path.exists():
            temp_output_path.unlink()
        raise

    elapsed = time.time() - t0
    size_gb = Path(output_path).stat().st_size / 1e9
    _log(verbose, progress_logger, f"\nDone in {elapsed:.0f}s, size={size_gb:.2f} GB")


def write_pyramidal_ometiff(
    output_path: str,
    pyramid: list[np.ndarray],
    mpp: float,
    *,
    tile_size: int = 512,
    compression: Optional[str] = "lzw",
    image_name: str = "Image",
    magnification: Optional[float] = None,
    verbose: bool = True,
    progress_logger: Optional[ProgressLogger] = None,
) -> None:
    """
    Write a pyramidal OME-TIFF with SubIFD-linked resolution levels.

    The public array-list API is preserved for tests and callers. Internally it
    delegates to the streaming tile writer so edge handling and SubIFD writing
    use the same code path as out-of-core conversion.
    """
    write_pyramidal_ometiff_from_levels(
        output_path,
        pyramid,
        mpp,
        tile_size=tile_size,
        compression=compression,
        image_name=image_name,
        magnification=magnification,
        verbose=verbose,
        progress_logger=progress_logger,
    )
