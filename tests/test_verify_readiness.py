"""Verifier checks for Xenium Explorer readiness reporting."""

from pathlib import Path

import numpy as np
import tifffile

from svs_to_ometiff import ConvertConfig, convert, verify_ometiff
from tests.helpers import write_synthetic_33007_svs


def test_verify_reports_tile_subifd_and_mpp_fields(tmp_path: Path) -> None:
    input_svs = tmp_path / "synthetic.svs"
    output = tmp_path / "out.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=32, height=32)

    convert(
        ConvertConfig(
            input_svs=str(input_svs),
            output_ometiff=str(output),
            tile_size=16,
            compression=None,
            num_levels=2,
            verbose=False,
        )
    )

    result = verify_ometiff(str(output), min_levels=2, expected_tile_size=16)

    assert result["pass"] is True
    assert result["is_ome"] is True
    assert result["is_bigtiff"] is True
    assert result["subifds"] == 1
    assert result["tile_width"] == 16
    assert result["tile_height"] == 16
    assert result["dtype"] == "uint8"
    assert result["physical_size_x"] == 0.5
    assert result["physical_size_y"] == 0.5


def test_verify_warns_when_mpp_missing_but_does_not_fail(tmp_path: Path) -> None:
    output = tmp_path / "missing_mpp.ome.tiff"
    data = np.zeros((16, 16, 3), dtype=np.uint8)
    tifffile.imwrite(
        output,
        data,
        bigtiff=True,
        ome=True,
        tile=(16, 16),
        photometric="rgb",
    )

    result = verify_ometiff(str(output), expected_tile_size=16)

    assert result["pass"] is True
    assert any("physical pixel size" in warning.lower() for warning in result["warnings"])
