"""
OME-TIFF writer with SubIFD pyramid linkage.

Writes a multi-resolution pyramidal OME-TIFF using tifffile's TiffWriter
with proper SubIFD structure. The subifds parameter on the full-resolution
IFD declares the sub-resolution levels, enabling proper pyramid detection
by downstream tools (tifffile, napari, QuPath, Xenium Explorer, etc.).
"""

import os
import time
from typing import Optional

import numpy as np
import tifffile


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
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"\n'
        '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '     xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06'
        ' http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">\n'
        f'  <Image ID="Image:0" Name="{image_name}">\n'
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
) -> None:
    """
    Write a pyramidal OME-TIFF with SubIFD-linked resolution levels.

    The full-resolution image (pyramid[0]) is written as the base IFD with
    ``subifds=N-1`` pointing to the sub-resolution levels. Each sub-level is
    written as a SubIFD with ``subfiletype=1`` (reduced-resolution image).
    This structure is detected as a proper pyramid by tifffile, napari,
    QuPath, and other tools.

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

    Raises:
        ValueError: If pyramid is empty or arrays have unexpected shapes.
        OSError: If the output file cannot be written.
    """
    if not pyramid:
        raise ValueError("pyramid must contain at least one level")

    full_img = pyramid[0]
    if full_img.ndim != 3 or full_img.shape[2] != 3:
        raise ValueError(
            f"Full-resolution image must be (H, W, 3), got {full_img.shape}"
        )
    if full_img.dtype != np.uint8:
        raise ValueError(f"Full-resolution image must be uint8, got {full_img.dtype}")

    full_h, full_w = full_img.shape[:2]

    # Build OME-XML (ASCII-compatible)
    ome_xml = build_ome_xml(full_w, full_h, mpp, image_name)

    # Remove existing file
    if os.path.exists(output_path):
        os.remove(output_path)
        if verbose:
            print(f"Removed existing file: {output_path}")

    if verbose:
        print(f"Writing pyramidal OME-TIFF with SubIFD linkage...")
        print(f"Levels: {[p.shape[:2] for p in pyramid]}")

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
        if verbose:
            print(f"  Level 0: {full_w}x{full_h} written")

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
            if verbose:
                print(f"  Level {level}: {img.shape[1]}x{img.shape[0]} written")

    elapsed = time.time() - t0
    size_gb = os.path.getsize(output_path) / 1e9

    if verbose:
        print(f"\nDone in {elapsed:.0f}s, size={size_gb:.2f} GB")
