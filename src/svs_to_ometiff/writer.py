"""
OME-TIFF writer with SubIFD pyramid linkage.

Writes a multi-resolution pyramidal OME-TIFF using tifffile's TiffWriter
with SubIFD structure. The subifds parameter on the full-resolution IFD
declares the sub-resolution levels, enabling pyramid detection in readers
that support SubIFD-linked pyramids.
"""

import os
import time
from collections.abc import Callable
from typing import Optional
from xml.sax.saxutils import quoteattr

import numpy as np
import tifffile

ProgressLogger = Callable[[str], None]


def _log(verbose: bool, logger: Optional[ProgressLogger], message: str) -> None:
    if not verbose:
        return
    if logger is None:
        print(message)
    else:
        logger(message)


def build_ome_xml(
    full_width: int,
    full_height: int,
    mpp: float,
    image_name: str = "Image",
) -> str:
    """
    Build OME-XML metadata string for embedding in the TIFF description tag.

    Uses 7-bit ASCII-compatible characters only (``um`` not ``µm``).

    Args:
        full_width: Image width in pixels at full resolution.
        full_height: Image height in pixels at full resolution.
        mpp: Microns per pixel.
        image_name: Name for the OME Image element.

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

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"\n'
        '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '     xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06'
        ' http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">\n'
        f"  <Image ID=\"Image:0\" Name={image_name_attr}>\n"
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


def write_pyramidal_ometiff(
    output_path: str,
    pyramid: list[np.ndarray],
    mpp: float,
    *,
    tile_size: int = 512,
    compression: Optional[str] = "lzw",
    image_name: str = "Image",
    verbose: bool = True,
    progress_logger: Optional[ProgressLogger] = None,
) -> None:
    """
    Write a pyramidal OME-TIFF with SubIFD-linked resolution levels.

    The full-resolution image (pyramid[0]) is written as the base IFD with
    ``subifds=N-1`` pointing to the sub-resolution levels. Each sub-level is
    written as a SubIFD with ``subfiletype=1`` (reduced-resolution image).
    This structure is detected as a pyramid by tifffile and should be
    compatible with readers that support SubIFD-linked pyramids.

    Uses BigTIFF format (required for images >4 GB), LZW lossless compression,
    and tiled storage.

    Args:
        output_path: Path for the output OME-TIFF file.
        pyramid: List of numpy arrays, pyramid[0] is full resolution,
                 pyramid[1:] are downsampled levels.
        mpp: Microns per pixel for the full-resolution level.
        tile_size: Output tile size (square, default 512).
        compression: TIFF compression scheme ('lzw', 'zlib', 'deflate', etc.),
            or None for uncompressed output.
        image_name: Name for the OME Image element.
        verbose: Print progress information.
        progress_logger: Optional callable used instead of print.

    Raises:
        ValueError: If pyramid is empty or arguments are invalid.
        OSError: If the output file cannot be written.
    """
    if not pyramid:
        raise ValueError("pyramid must contain at least one level")
    if tile_size <= 0:
        raise ValueError(f"tile_size must be positive, got {tile_size}")
    if tile_size % 16 != 0:
        raise ValueError(
            f"tile_size must be divisible by 16 for tiled TIFF output, got {tile_size}"
        )
    if mpp <= 0:
        raise ValueError(f"mpp must be positive, got {mpp}")

    full_img = pyramid[0]
    for level, img in enumerate(pyramid):
        if img.ndim != 3 or img.shape[2] != 3:
            raise ValueError(f"Pyramid level {level} must be (H, W, 3), got {img.shape}")
        if img.dtype != np.uint8:
            raise ValueError(f"Pyramid level {level} must be uint8, got {img.dtype}")
        if img.shape[0] <= 0 or img.shape[1] <= 0:
            raise ValueError(f"Pyramid level {level} has empty dimensions: {img.shape}")

    full_h, full_w = full_img.shape[:2]

    # Build OME-XML (ASCII-compatible)
    ome_xml = build_ome_xml(full_w, full_h, mpp, image_name)

    # Remove existing file
    if os.path.exists(output_path):
        os.remove(output_path)
        _log(verbose, progress_logger, f"Removed existing file: {output_path}")

    _log(verbose, progress_logger, "Writing pyramidal OME-TIFF with SubIFD linkage...")
    _log(verbose, progress_logger, f"Levels: {[p.shape[:2] for p in pyramid]}")

    t0 = time.time()

    n_subifds = len(pyramid) - 1  # Number of sub-resolution levels

    with tifffile.TiffWriter(output_path, bigtiff=True) as tif:
        # Write full-resolution level 0 with subifds declaration
        tif.write(
            full_img,
            description=ome_xml,
            subifds=n_subifds,
            tile=(tile_size, tile_size),
            compression=compression,
            photometric="rgb",
            metadata=None,
            resolution=(1e4 / mpp, 1e4 / mpp),
            resolutionunit=tifffile.RESUNIT.CENTIMETER,
        )
        _log(verbose, progress_logger, f"  Level 0: {full_w}x{full_h} written")

        # Write sub-resolution levels as SubIFDs
        for level in range(1, len(pyramid)):
            img = pyramid[level]
            tif.write(
                img,
                subfiletype=1,  # Reduced-resolution image
                tile=(tile_size, tile_size),
                compression=compression,
                photometric="rgb",
                metadata=None,
            )
            _log(
                verbose,
                progress_logger,
                f"  Level {level}: {img.shape[1]}x{img.shape[0]} written",
            )

    elapsed = time.time() - t0
    size_gb = os.path.getsize(output_path) / 1e9

    _log(verbose, progress_logger, f"\nDone in {elapsed:.0f}s, size={size_gb:.2f} GB")
