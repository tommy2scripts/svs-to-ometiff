"""Single-file CLI disk preflight behavior."""

from pathlib import Path

from click.testing import CliRunner

from svs_to_ometiff import cli as single_cli
from svs_to_ometiff.preflight import PreflightError


def test_preflight_only_does_not_convert_or_create_output(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    def fake_read_metadata(path: str):
        return {
            "width": 100,
            "height": 100,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fake_check_preflight(**kwargs):
        return single_cli.PreflightResult(
            source_width=100,
            source_height=100,
            full_res_rgb_bytes=30_000,
            pyramid_rgb_bytes=37_500,
            required_temp_bytes=45_000,
            required_output_bytes=45_000,
            available_temp_bytes=1_000_000,
            available_output_bytes=1_000_000,
            safety_factor=1.2,
            pass_=True,
            errors=[],
        )

    monkeypatch.setattr(single_cli, "convert", fake_convert)
    monkeypatch.setattr(single_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(single_cli, "check_preflight", fake_check_preflight)
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    output = tmp_path / "slide.ome.tiff"

    result = CliRunner().invoke(
        single_cli.main,
        [str(input_svs), str(output), "--preflight-only", "--quiet"],
    )

    assert result.exit_code == 0
    assert "Preflight: PASS" in result.output
    assert calls == []
    assert not output.exists()


def test_no_preflight_bypasses_preflight_check(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    def fail_preflight(**kwargs):
        raise AssertionError("preflight should not run")

    monkeypatch.setattr(single_cli, "convert", fake_convert)
    monkeypatch.setattr(single_cli, "check_preflight", fail_preflight)
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    output = tmp_path / "slide.ome.tiff"

    result = CliRunner().invoke(
        single_cli.main,
        [str(input_svs), str(output), "--no-preflight", "--quiet"],
    )

    assert result.exit_code == 0
    assert len(calls) == 1


def test_preflight_failure_stops_before_conversion(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_convert(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    def fake_read_metadata(path: str):
        return {
            "width": 100,
            "height": 100,
            "compression": 33007,
            "mpp": 0.5,
        }

    def fail_preflight(**kwargs):
        raise PreflightError(
            "Insufficient temp space. Required ~1.0 GB, available 0.1 GB. "
            "Use --temp-dir on a larger local SSD."
        )

    monkeypatch.setattr(single_cli, "convert", fake_convert)
    monkeypatch.setattr(single_cli, "read_svs_metadata", fake_read_metadata)
    monkeypatch.setattr(single_cli, "check_preflight", fail_preflight)
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    output = tmp_path / "slide.ome.tiff"

    result = CliRunner().invoke(
        single_cli.main,
        [str(input_svs), str(output), "--quiet"],
    )

    assert result.exit_code == 1
    assert "Insufficient temp space" in result.output
    assert calls == []


def test_preflight_only_and_no_preflight_conflict(tmp_path: Path) -> None:
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    output = tmp_path / "slide.ome.tiff"

    result = CliRunner().invoke(
        single_cli.main,
        [str(input_svs), str(output), "--preflight-only", "--no-preflight"],
    )

    assert result.exit_code == 2
    assert "--preflight-only and --no-preflight are mutually exclusive" in result.output
