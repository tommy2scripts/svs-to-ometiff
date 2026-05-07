"""Release metadata consistency tests."""

from pathlib import Path
import inspect
import re

from click.testing import CliRunner

import svs_to_ometiff
import svs_to_ometiff.cli as cli_module
from svs_to_ometiff.cli import _print_experimental_warning, main


_VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"$', re.MULTILINE)


def _pyproject_version() -> str:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    match = _VERSION_RE.search(pyproject.read_text(encoding="utf-8"))
    assert match is not None, "project.version missing from pyproject.toml"
    return match.group("version")


def test_pyproject_version_matches_package_version() -> None:
    assert _pyproject_version() == svs_to_ometiff.__version__


def test_cli_version_includes_package_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert svs_to_ometiff.__version__ in result.output


def test_cli_uses_package_version_metadata() -> None:
    source = inspect.getsource(cli_module)

    assert "from svs_to_ometiff import __version__" in source
    assert 'version="0.4.0"' not in source
    assert "v0.4.0" not in source


def test_experimental_warning_mentions_package_version(capsys) -> None:
    _print_experimental_warning()

    captured = capsys.readouterr()
    assert svs_to_ometiff.__version__ in captured.err


def test_experimental_warning_reads_current_package_version(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_module, "__version__", "9.9.9-test", raising=False)

    _print_experimental_warning()

    captured = capsys.readouterr()
    assert "9.9.9-test" in captured.err
