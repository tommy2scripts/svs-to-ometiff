"""Tests for source-aware verification and deep pixel validation."""

import json
from pathlib import Path
import numpy as np
from click.testing import CliRunner

from svs_to_ometiff import verify as verify_cli
from svs_to_ometiff.verify import (
    verify_ometiff,
)


class MockTiffPage:
    def __init__(self, tile_width=1024, tile_height=1024):
        self.tilewidth = tile_width
        self.tilelength = tile_height
        self.tags = {}


class MockLevel:
    def __init__(self, shape, dtype="uint8", data=None):
        self.shape = shape
        self.dtype = dtype
        self._data = data

    def asarray(self):
        if self._data is not None:
            return self._data
        return np.ones((self.shape[0], self.shape[1], 3), dtype=self.dtype)


class MockSeries:
    def __init__(self, levels):
        self.levels = levels


class FakeTiffFile:
    def __init__(self, is_ome=True, is_bigtiff=True, series=None, pages=None, ome_metadata=""):
        self.is_ome = is_ome
        self.is_bigtiff = is_bigtiff
        self.series = series or []
        self.pages = pages or []
        self.ome_metadata = ome_metadata

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_verify_ometiff_passes_when_matches_source(monkeypatch, tmp_path: Path) -> None:
    # 1. Setup mock SVS metadata
    def fake_read_metadata(path: str):
        return {
            "width": 1000,
            "height": 1000,
            "mpp": 0.5,
            "magnification": 40.0,
        }

    # 2. Setup mock OME-XML
    xml_data = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">\n'
        '  <Instrument ID="Instrument:0">\n'
        '    <Objective ID="Objective:0" NominalMagnification="40"/>\n'
        '  </Instrument>\n'
        '  <Image ID="Image:0" Name="slide">\n'
        '    <Pixels ID="Pixels:0" PhysicalSizeX="0.5" PhysicalSizeY="0.5">\n'
        '    </Pixels>\n'
        '  </Image>\n'
        '</OME>'
    )

    # 3. Setup mock TiffFile
    levels = [
        MockLevel((1000, 1000, 3)),
        MockLevel((500, 500, 3)),
    ]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]
    
    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages, ome_metadata=xml_data)

    monkeypatch.setattr(verify_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy_output.ome.tiff",
        source_path="dummy_source.svs",
        expected_tile_size=1024,
    )

    assert result["pass"] is True
    assert result["errors"] == []
    assert result["physical_size_x"] == 0.5


def test_verify_ometiff_fails_on_dimension_mismatch(monkeypatch, tmp_path: Path) -> None:
    def fake_read_metadata(path: str):
        return {"width": 1000, "height": 1000}

    levels = [MockLevel((500, 500, 3))]  # 500x500 does not match 1000x1000
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy_output.ome.tiff",
        source_path="dummy_source.svs",
    )

    assert result["pass"] is False
    assert any("dimensions" in err for err in result["errors"])


def test_verify_ometiff_fails_on_mpp_mismatch(monkeypatch, tmp_path: Path) -> None:
    def fake_read_metadata(path: str):
        return {"width": 1000, "height": 1000, "mpp": 0.5}

    xml_data = (
        '<OME>\n'
        '  <Image>\n'
        '    <Pixels PhysicalSizeX="0.6" PhysicalSizeY="0.6"></Pixels>\n'
        '  </Image>\n'
        '</OME>'
    )

    levels = [MockLevel((1000, 1000, 3))]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages, ome_metadata=xml_data)

    monkeypatch.setattr(verify_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy_output.ome.tiff",
        source_path="dummy_source.svs",
        tolerance=1e-3,
    )

    assert result["pass"] is False
    assert any("MPP" in err or "mpp" in err.lower() for err in result["errors"])


def test_verify_ometiff_fails_on_magnification_mismatch(monkeypatch, tmp_path: Path) -> None:
    def fake_read_metadata(path: str):
        return {"width": 1000, "height": 1000, "magnification": 40.0}

    xml_data = (
        '<OME>\n'
        '  <Instrument>\n'
        '    <Objective NominalMagnification="20"></Objective>\n'
        '  </Instrument>\n'
        '</OME>'
    )

    levels = [MockLevel((1000, 1000, 3))]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages, ome_metadata=xml_data)

    monkeypatch.setattr(verify_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy_output.ome.tiff",
        source_path="dummy_source.svs",
    )

    assert result["pass"] is False
    assert any("magnification" in err for err in result["errors"])


def test_verify_deep_checks_detect_empty_black_image(monkeypatch) -> None:
    # All zero array triggers deep check failure
    black_data = np.zeros((10, 10, 3), dtype=np.uint8)
    levels = [MockLevel((10, 10, 3), data=black_data)]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy.ome.tiff",
        deep=True,
    )

    assert result["pass"] is False
    assert any("entirely empty/black" in err for err in result["errors"])


def test_verify_deep_checks_detect_low_variance_warning(monkeypatch) -> None:
    # Uniform solid color triggers low variance warning
    solid_data = np.ones((10, 10, 3), dtype=np.uint8) * 128
    levels = [MockLevel((10, 10, 3), data=solid_data)]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = verify_ometiff(
        "dummy.ome.tiff",
        deep=True,
    )

    assert result["pass"] is True
    assert len(result["warnings"]) > 0
    assert any("variance" in warn for warn in result["warnings"])


def test_strict_mode_escalates_warnings_to_errors(monkeypatch, tmp_path: Path) -> None:
    levels = [MockLevel((10, 10, 3))]
    series = [MockSeries(levels)]
    # Mismatching tile size triggers a warning
    pages = [MockTiffPage(tile_width=512, tile_height=512)]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    dummy_file = tmp_path / "dummy.ome.tiff"
    dummy_file.write_bytes(b"dummy")

    # Strict flag raises failure
    result = CliRunner().invoke(
        verify_cli.main,
        [str(dummy_file), "--strict", "--json"],
    )

    assert result.exit_code == 1
    json_res = json.loads(result.output)
    assert json_res["pass"] is False
    assert any("Strict mode:" in err for err in json_res["errors"])


def test_json_output_cli_formatting(monkeypatch, tmp_path: Path) -> None:
    levels = [MockLevel((100, 100, 3))]
    series = [MockSeries(levels)]
    pages = [MockTiffPage(tile_width=1024, tile_height=1024)]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    dummy_file = tmp_path / "dummy.ome.tiff"
    dummy_file.write_bytes(b"dummy")

    result = CliRunner().invoke(
        verify_cli.main,
        [str(dummy_file), "--json"],
    )

    assert result.exit_code == 0
    json_res = json.loads(result.output)
    assert json_res["is_ome"] is True
    assert json_res["is_bigtiff"] is True
    assert json_res["levels"] == [[100, 100, 3]]
    assert json_res["pass"] is True
