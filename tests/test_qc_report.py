"""Tests for standalone HTML QC report generation."""

from pathlib import Path
from click.testing import CliRunner

from svs_to_ometiff import verify as verify_cli
from svs_to_ometiff.qc_report import generate_qc_html


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
        import numpy as np
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


def test_generate_qc_html_basic_reporting(monkeypatch) -> None:
    levels = [MockLevel((100, 100, 3))]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    result = {
        "pass": True,
        "is_ome": True,
        "is_bigtiff": True,
        "levels": [[100, 100, 3]],
        "subifds": 0,
        "tile_width": 1024,
        "tile_height": 1024,
        "dtype": "uint8",
        "physical_size_x": 0.5,
        "physical_size_y": 0.5,
        "errors": [],
        "warnings": ["Warning: testing escaping <script>"],
    }

    html_content = generate_qc_html("slide.ome.tiff", result, source_path="slide.svs")

    assert "slide.ome.tiff" in html_content
    assert "slide.svs" in html_content
    assert "Non-Diagnostic Disclaimer" in html_content
    assert "100 x 100" in html_content
    # Safe escaping test
    assert "&lt;script&gt;" in html_content
    assert "<script>" not in html_content


def test_verify_cli_generates_html_report_file(monkeypatch, tmp_path: Path) -> None:
    levels = [MockLevel((100, 100, 3))]
    series = [MockSeries(levels)]
    pages = [MockTiffPage()]

    def fake_tifffile_open(path):
        return FakeTiffFile(series=series, pages=pages)

    monkeypatch.setattr(verify_cli.tifffile, "TiffFile", fake_tifffile_open)

    dummy_file = tmp_path / "dummy.ome.tiff"
    dummy_file.write_bytes(b"dummy")
    html_report = tmp_path / "report.html"

    result = CliRunner().invoke(
        verify_cli.main,
        [str(dummy_file), "--html", str(html_report)],
    )

    assert result.exit_code == 0
    assert html_report.exists()
    
    report_content = html_report.read_text(encoding="utf-8")
    assert "dummy.ome.tiff" in report_content
    assert "Non-Diagnostic Disclaimer" in report_content
    assert "Pyramid Geometry" in report_content
