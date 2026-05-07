"""Tests for svs_to_ometiff.verify module."""

from pathlib import Path

import numpy as np
import tifffile
from click.testing import CliRunner

from svs_to_ometiff.verify import main, verify_ometiff
from svs_to_ometiff.writer import write_pyramidal_ometiff


def _make_rgb(height: int, width: int) -> np.ndarray:
    """Create a deterministic RGB image."""
    y, x = np.indices((height, width), dtype=np.uint16)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = (x % 256).astype(np.uint8)
    image[..., 1] = (y % 256).astype(np.uint8)
    image[..., 2] = ((x + y) % 256).astype(np.uint8)
    return image


def test_verify_ometiff_accepts_valid_rgb_ome_pyramid(tmp_path: Path) -> None:
    """verify_ometiff passes for a valid pyramidal OME-TIFF with 2 levels."""
    output = tmp_path / "test_pyramid.ome.tiff"
    level0 = _make_rgb(32, 48)
    level1 = (
        level0.reshape(16, 2, 24, 2, 3).mean(axis=(1, 3)).astype(np.uint8)
    )

    write_pyramidal_ometiff(
        str(output),
        [level0, level1],
        mpp=0.5,
        tile_size=16,
        compression=None,
        image_name="test",
        verbose=False,
    )

    result = verify_ometiff(str(output), min_levels=2)

    assert result["is_ome"] is True
    assert result["is_bigtiff"] is True
    assert len(result["levels"]) == 2
    assert result["dtype"] == "uint8"
    assert result["pass"] is True


def test_verify_cli_reports_pass(tmp_path: Path) -> None:
    """CLI exits 0 and prints PASS for a valid OME-TIFF."""
    output = tmp_path / "test_single.ome.tiff"
    level0 = _make_rgb(32, 32)

    write_pyramidal_ometiff(
        str(output),
        [level0],
        mpp=0.5,
        tile_size=16,
        compression=None,
        image_name="test",
        verbose=False,
    )

    runner = CliRunner()
    result = runner.invoke(main, [str(output)])

    assert result.exit_code == 0
    assert "PASS" in result.output


def test_verify_ometiff_fails_on_non_ome_tiff(tmp_path: Path) -> None:
    """verify_ometiff fails for a regular (non-OME) TIFF."""
    output = tmp_path / "regular.tiff"
    image = _make_rgb(16, 16)

    with tifffile.TiffWriter(output) as tif:
        tif.write(image, photometric="rgb", metadata=None)

    result = verify_ometiff(str(output))

    assert result["is_ome"] is False
    assert result["pass"] is False
