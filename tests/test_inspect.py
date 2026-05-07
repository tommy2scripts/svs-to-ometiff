"""Tests for the SVS inspection module."""

from pathlib import Path

from click.testing import CliRunner

from svs_to_ometiff.inspect import inspect_svs, main

from helpers import write_synthetic_33007_svs


def test_inspect_svs_reports_required_metadata(tmp_path: Path) -> None:
    """inspect_svs returns correct metadata for a synthetic 33007 SVS."""
    svs_path = tmp_path / "test.svs"
    write_synthetic_33007_svs(svs_path, width=32, height=24)

    result = inspect_svs(str(svs_path))

    assert result["compression"] == 33007
    assert result["width"] == 32
    assert result["height"] == 24
    assert result["convertible"] is True


def test_inspect_cli_prints_convertible_status(tmp_path: Path) -> None:
    """CLI prints compression and convertible status for a valid SVS."""
    svs_path = tmp_path / "test.svs"
    write_synthetic_33007_svs(svs_path, width=32, height=24)

    runner = CliRunner()
    result = runner.invoke(main, [str(svs_path)])

    assert result.exit_code == 0
    assert "Compression: 33007" in result.output
    assert "Convertible: yes" in result.output
