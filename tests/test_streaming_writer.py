"""Tests for streamed/out-of-core OME-TIFF writing."""

from pathlib import Path

import numpy as np
import tifffile

from svs_to_ometiff.writer import write_pyramidal_ometiff_from_levels


def _rgb_gradient(height: int, width: int) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.uint16)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = (x % 256).astype(np.uint8)
    image[..., 1] = (y % 256).astype(np.uint8)
    image[..., 2] = ((x + y) % 256).astype(np.uint8)
    return image


def test_streaming_writer_preserves_pixels_and_pyramid_structure(tmp_path: Path) -> None:
    output = tmp_path / "streamed.ome.tiff"
    level0 = _rgb_gradient(30, 34)
    level1 = level0[:30, :34].reshape(15, 2, 17, 2, 3).mean(axis=(1, 3)).astype(np.uint8)

    write_pyramidal_ometiff_from_levels(
        str(output),
        [level0, level1],
        0.5,
        tile_size=16,
        compression=None,
        image_name="streaming-writer",
        verbose=False,
    )

    with tifffile.TiffFile(output) as tif:
        assert tif.is_ome
        assert tif.is_bigtiff
        assert len(tif.series[0].levels) == 2
        np.testing.assert_array_equal(tif.series[0].levels[0].asarray(), level0)
        np.testing.assert_array_equal(tif.series[0].levels[1].asarray(), level1)


def test_streaming_writer_supports_single_resolution_output(tmp_path: Path) -> None:
    output = tmp_path / "single.ome.tiff"
    level0 = _rgb_gradient(16, 16)

    write_pyramidal_ometiff_from_levels(
        str(output),
        [level0],
        0.5,
        tile_size=16,
        compression=None,
        image_name="single-resolution",
        verbose=False,
    )

    with tifffile.TiffFile(output) as tif:
        assert tif.is_ome
        assert len(tif.series[0].levels) == 1
        np.testing.assert_array_equal(tif.series[0].levels[0].asarray(), level0)
