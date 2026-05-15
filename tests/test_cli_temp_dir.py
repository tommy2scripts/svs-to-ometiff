"""CLI tests for temp-dir option wiring."""

from pathlib import Path

from click.testing import CliRunner

from svs_to_ometiff import batch as batch_cli
from svs_to_ometiff import cli as single_cli


def test_single_cli_exposes_one_temp_dir_option() -> None:
    runner = CliRunner()
    result = runner.invoke(single_cli.main, ["--help"])
    temp_options = [
        param
        for param in single_cli.main.params
        if getattr(param, "name", None) == "temp_dir"
    ]

    assert result.exit_code == 0
    assert len(temp_options) == 1


def test_single_cli_passes_temp_dir(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_convert(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"pyramid_shapes": []}

    monkeypatch.setattr(single_cli, "convert", fake_convert)
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    output = tmp_path / "slide.ome.tiff"
    temp_dir = tmp_path / "local_tmp"

    runner = CliRunner()
    result = runner.invoke(
        single_cli.main,
        [
            str(input_svs),
            str(output),
            "--temp-dir",
            str(temp_dir),
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["temp_dir"] == str(temp_dir)


def test_batch_cli_exposes_one_temp_dir_option() -> None:
    runner = CliRunner()
    result = runner.invoke(batch_cli.main, ["--help"])
    temp_options = [
        param
        for param in batch_cli.main.params
        if getattr(param, "name", None) == "temp_dir"
    ]

    assert result.exit_code == 0
    assert len(temp_options) == 1


def test_batch_cli_passes_temp_dir(monkeypatch, tmp_path: Path) -> None:
    captured = []

    def fake_convert(*args, **kwargs):
        captured.append((args, kwargs))
        return {"pyramid_shapes": []}

    monkeypatch.setattr(batch_cli, "convert", fake_convert)
    input_svs = tmp_path / "slide.svs"
    input_svs.write_bytes(b"not used")
    temp_dir = tmp_path / "local_tmp"

    runner = CliRunner()
    result = runner.invoke(
        batch_cli.main,
        [
            str(tmp_path),
            "--temp-dir",
            str(temp_dir),
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert len(captured) == 1
    assert captured[0][1]["temp_dir"] == str(temp_dir)
