"""Tests for batch disk-space preflight integration and manifest reporting."""

import json
from pathlib import Path
from click.testing import CliRunner

from svs_to_ometiff import batch as batch_cli


def _touch_svs(path: Path) -> Path:
    path.write_bytes(b"not used")
    return path


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_batch_preflight_passes_with_mocked_disk_usage(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        # Create a dummy output file so verification or size checks don't crash
        out_path = Path(args[1])
        out_path.write_text("output data", encoding="utf-8")
        return {"width": 100, "height": 100, "output_size_bytes": 11}

    def fake_read_metadata(path: str):
        return {
            "width": 20000,
            "height": 20000,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fake_disk_usage(path: str):
        return (10_000_000_000, 0, 10_000_000_000)

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr("shutil.disk_usage", fake_disk_usage)

    _touch_svs(tmp_path / "slide1.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    assert len(convert_calls) == 1

    records = _load_manifest(manifest)["records"]
    assert len(records) == 1
    assert records[0]["status"] == "converted"
    assert records[0]["preflight_pass"] is True
    assert records[0]["preflight_required_temp_gb"] > 0
    assert records[0]["preflight_required_output_gb"] > 0
    assert records[0]["preflight_errors"] == []


def test_batch_preflight_fails_when_space_is_insufficient(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        return {}

    def fake_read_metadata(path: str):
        return {
            "width": 10000,
            "height": 10000,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fake_disk_usage(path: str):
        # Return extremely low available bytes (e.g. 1 byte) to trigger failure
        return (10_000_000_000, 0, 1)

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr("shutil.disk_usage", fake_disk_usage)

    _touch_svs(tmp_path / "slide1.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 1
    assert len(convert_calls) == 0

    records = _load_manifest(manifest)["records"]
    assert len(records) == 1
    assert records[0]["status"] == "failed"
    assert records[0]["preflight_pass"] is False
    assert len(records[0]["preflight_errors"]) > 0
    assert any("Insufficient temp space" in err for err in records[0]["preflight_errors"])


def test_batch_preflight_only_does_not_convert_or_create_output(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        return {}

    def fake_read_metadata(path: str):
        return {
            "width": 100,
            "height": 100,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fake_disk_usage(path: str):
        return (10_000_000_000, 0, 10_000_000_000)

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr("shutil.disk_usage", fake_disk_usage)

    _touch_svs(tmp_path / "slide1.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--preflight-only", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    assert len(convert_calls) == 0

    records = _load_manifest(manifest)["records"]
    assert len(records) == 1
    assert records[0]["status"] == "preflight_passed"
    assert records[0]["preflight_pass"] is True
    assert not (tmp_path / "slide1.ome.tiff").exists()


def test_batch_preflight_continue_on_error(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        out_path = Path(args[1])
        out_path.write_text("output", encoding="utf-8")
        return {"width": 20000, "height": 20000, "output_size_bytes": 6}

    def fake_read_metadata(path: str):
        return {
            "width": 20000,
            "height": 20000,
            "compression": 33007,
            "mpp": 0.5,
        }

    # First file has insufficient space, second has sufficient space
    call_count = 0
    def fake_disk_usage(path: str):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return (1_000, 0, 1)
        else:
            return (10_000_000_000, 0, 10_000_000_000)

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr("shutil.disk_usage", fake_disk_usage)

    _touch_svs(tmp_path / "slide1.svs")
    _touch_svs(tmp_path / "slide2.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--continue-on-error", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 1  # Fails overall because slide1 failed
    assert len(convert_calls) == 1  # Only slide2 converted

    records = _load_manifest(manifest)["records"]
    assert len(records) == 2
    assert records[0]["input_path"].endswith("slide1.svs")
    assert records[0]["status"] == "failed"
    assert records[0]["preflight_pass"] is False

    assert records[1]["input_path"].endswith("slide2.svs")
    assert records[1]["status"] == "converted"
    assert records[1]["preflight_pass"] is True


def test_batch_preflight_fail_fast(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        return {}

    def fake_read_metadata(path: str):
        return {
            "width": 20000,
            "height": 20000,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fake_disk_usage(path: str):
        return (1000, 0, 1)  # All fail preflight

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr("shutil.disk_usage", fake_disk_usage)

    _touch_svs(tmp_path / "slide1.svs")
    _touch_svs(tmp_path / "slide2.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--fail-fast", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 1
    assert len(convert_calls) == 0

    records = _load_manifest(manifest)["records"]
    # Should stop after the first file failure under fail_fast
    assert len(records) == 1
    assert records[0]["input_path"].endswith("slide1.svs")
    assert records[0]["status"] == "failed"


def test_batch_preflight_no_preflight_bypasses(monkeypatch, tmp_path: Path) -> None:
    convert_calls = []

    def fake_convert(*args, **kwargs):
        convert_calls.append(args)
        out_path = Path(args[1])
        out_path.write_text("output", encoding="utf-8")
        return {"width": 100, "height": 100, "output_size_bytes": 6}

    def fake_check_preflight(**kwargs):
        raise AssertionError("preflight check should be bypassed")

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    monkeypatch.setattr(batch_cli, "check_preflight", fake_check_preflight)

    _touch_svs(tmp_path / "slide1.svs")
    manifest = tmp_path / "manifest.json"

    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--no-preflight", "--manifest", str(manifest), "--quiet"],
    )

    assert result.exit_code == 0
    assert len(convert_calls) == 1

    records = _load_manifest(manifest)["records"]
    assert len(records) == 1
    assert records[0]["status"] == "converted"
    assert records[0]["preflight_pass"] is None


def test_batch_preflight_only_and_no_preflight_conflict(tmp_path: Path) -> None:
    _touch_svs(tmp_path / "slide1.svs")
    result = CliRunner().invoke(
        batch_cli.main,
        [str(tmp_path), "--preflight-only", "--no-preflight"],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output
