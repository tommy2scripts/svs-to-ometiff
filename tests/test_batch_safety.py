"""Batch CLI safety, rerun, and manifest behavior."""

import json
from pathlib import Path

from click.testing import CliRunner

from svs_to_ometiff import batch as batch_cli


def _touch_svs(path: Path) -> Path:
    path.write_bytes(b"not used")
    return path


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_existing_output_without_flags_does_not_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        return {"width": 10, "height": 20}

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    _touch_svs(tmp_path / "slide.svs")
    output = tmp_path / "slide.ome.tiff"
    output.write_text("existing", encoding="utf-8")

    result = CliRunner().invoke(batch_cli.main, [str(tmp_path), "--quiet"])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert output.read_text(encoding="utf-8") == "existing"
    assert calls == []


def test_skip_existing_skips_and_records_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        return {"width": 10, "height": 20}

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    _touch_svs(tmp_path / "slide.svs")
    (tmp_path / "slide.ome.tiff").write_text("existing", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--skip-existing", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    assert calls == []
    records = _load_manifest(manifest)["records"]
    assert [record["status"] for record in records] == ["skipped_existing"]
    assert records[0]["verify_pass"] is None


def test_force_allows_existing_output_conversion(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        Path(args[1]).write_text("new", encoding="utf-8")
        return {"width": 10, "height": 20, "output_size_bytes": 3}

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    _touch_svs(tmp_path / "slide.svs")
    output = tmp_path / "slide.ome.tiff"
    output.write_text("existing", encoding="utf-8")

    result = CliRunner().invoke(batch_cli.main, [str(tmp_path), "--force", "--quiet"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert output.read_text(encoding="utf-8") == "new"


def test_manifest_is_written_after_success(monkeypatch, tmp_path: Path) -> None:
    def fake_convert(*args, **kwargs):
        Path(args[1]).write_text("output", encoding="utf-8")
        return {
            "width": 10,
            "height": 20,
            "mpp": 0.5,
            "compression": 33007,
            "convertible": True,
            "output_size_bytes": 6,
        }

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    _touch_svs(tmp_path / "slide.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    records = _load_manifest(manifest)["records"]
    assert [record["status"] for record in records] == ["converted"]
    assert records[0]["source_width"] == 10
    assert records[0]["source_height"] == 20
    assert records[0]["source_mpp_x"] == 0.5
    assert records[0]["source_mpp_y"] == 0.5
    assert records[0]["source_compression"] == 33007
    assert records[0]["output_size_bytes"] == 6


def test_manifest_is_written_after_failure_with_continue_on_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_convert(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    _touch_svs(tmp_path / "slide.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--continue-on-error", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 1
    records = _load_manifest(manifest)["records"]
    assert [record["status"] for record in records] == ["failed"]
    assert records[0]["exception_type"] == "RuntimeError"
    assert records[0]["exception_message"] == "synthetic failure"


def test_continue_on_error_and_fail_fast_conflict_is_clean() -> None:
    result = CliRunner().invoke(
        batch_cli.main,
        ["slides", "--continue-on-error", "--fail-fast"],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_verify_records_verify_failed_status(monkeypatch, tmp_path: Path) -> None:
    def fake_convert(*args, **kwargs):
        Path(args[1]).write_text("output", encoding="utf-8")
        return {"width": 10, "height": 20, "output_size_bytes": 6}

    def fake_verify(*args, **kwargs):
        return {
            "pass": False,
            "warnings": ["warn"],
            "errors": ["bad"],
        }

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "verify_ometiff", fake_verify)
    _touch_svs(tmp_path / "slide.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--verify", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 1
    records = _load_manifest(manifest)["records"]
    assert [record["status"] for record in records] == ["verify_failed"]
    assert records[0]["verify_pass"] is False
    assert records[0]["verify_warnings"] == ["warn"]
    assert records[0]["verify_errors"] == ["bad"]


def test_batch_status_values_are_deterministic(monkeypatch, tmp_path: Path) -> None:
    names = ["b.svs", "a.svs"]

    def fake_convert(*args, **kwargs):
        Path(args[1]).write_text("output", encoding="utf-8")
        return {"output_size_bytes": 6}

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    for name in names:
        _touch_svs(tmp_path / name)
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    records = _load_manifest(manifest)["records"]
    assert [Path(record["input_path"]).name for record in records] == ["a.svs", "b.svs"]
    assert [record["status"] for record in records] == ["converted", "converted"]
