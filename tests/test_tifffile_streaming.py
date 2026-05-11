"""Spike tests documenting tifffile streamed tiled SubIFD writes."""

from pathlib import Path

import numpy as np
import tifffile

from svs_to_ometiff.writer import build_ome_xml


def _rgb_gradient(height: int, width: int) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.uint16)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = (x % 256).astype(np.uint8)
    image[..., 1] = (y % 256).astype(np.uint8)
    image[..., 2] = ((x + y) % 256).astype(np.uint8)
    return image


def _downsample_2x(image: np.ndarray) -> np.ndarray:
    h = image.shape[0] // 2
    w = image.shape[1] // 2
    return image[: h * 2, : w * 2].reshape(h, 2, w, 2, 3).mean(axis=(1, 3)).astype(np.uint8)


def _tile_iterator(image: np.ndarray, tile_size: int):
    for y0 in range(0, image.shape[0], tile_size):
        for x0 in range(0, image.shape[1], tile_size):
            yield image[y0 : y0 + tile_size, x0 : x0 + tile_size]


def test_tifffile_can_stream_tiled_rgb_subifd_pyramid(tmp_path: Path) -> None:
    """Document that tifffile accepts tile iterators with SubIFD pyramid linkage."""
    output = tmp_path / "streamed-subifd.ome.tiff"
    tile_size = 16
    level0 = _rgb_gradient(32, 32)
    level1 = _downsample_2x(level0)
    ome_xml = build_ome_xml(level0.shape[1], level0.shape[0], 0.5, "stream-spike")

    with tifffile.TiffWriter(output, bigtiff=True) as tif:
        tif.write(
            _tile_iterator(level0, tile_size),
            shape=level0.shape,
            dtype=level0.dtype,
            description=ome_xml,
            subifds=1,
            tile=(tile_size, tile_size),
            compression=None,
            photometric="rgb",
            metadata=None,
        )
        tif.write(
            _tile_iterator(level1, tile_size),
            shape=level1.shape,
            dtype=level1.dtype,
            subfiletype=1,
            tile=(tile_size, tile_size),
            compression=None,
            photometric="rgb",
            metadata=None,
        )

    with tifffile.TiffFile(output) as tif:
        assert tif.is_ome
        assert tif.is_bigtiff
        assert len(tif.series[0].levels) == 2
        assert tif.series[0].levels[0].shape == level0.shape
        assert tif.series[0].levels[1].shape == level1.shape
        np.testing.assert_array_equal(tif.series[0].levels[0].asarray(), level0)
        np.testing.assert_array_equal(tif.series[0].levels[1].asarray(), level1)
