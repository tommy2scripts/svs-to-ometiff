"""Tests for _resolve_path — the path resolution logic in serve.py."""

import os
from pathlib import Path
from unittest.mock import patch

from svs_to_ometiff_gui.serve import _resolve_path


class TestResolvePathAbsolute:
    """Paths that are already absolute and exist on disk."""

    def test_absolute_path_to_existing_file(self, tmp_svs):
        """An absolute path to an existing file returns that path."""
        result = _resolve_path(str(tmp_svs))
        assert result == str(tmp_svs)

    def test_absolute_path_to_missing_file(self, tmp_path):
        """An absolute path to a nonexistent file returns None."""
        missing = tmp_path / "does_not_exist.svs"
        assert _resolve_path(str(missing)) is None


class TestResolvePathBareFilename:
    """Bare filenames (no directory separators) trigger the common-dir search."""

    def test_bare_filename_found_in_downloads(self, tmp_path, monkeypatch):
        """A bare filename found in ~/Downloads is resolved."""
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        slide = downloads / "slide.svs"
        slide.write_bytes(b"FAKE")

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        result = _resolve_path("slide.svs")
        assert result == str(slide)

    def test_bare_filename_found_in_desktop(self, tmp_path, monkeypatch):
        """A bare filename found in ~/Desktop is resolved."""
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        slide = desktop / "slide.svs"
        slide.write_bytes(b"FAKE")

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        result = _resolve_path("slide.svs")
        assert result == str(slide)

    def test_bare_filename_not_found_anywhere(self, tmp_path, monkeypatch):
        """A bare filename that doesn't exist in any common dir returns None."""
        # Create the dirs but don't put the file in them
        (tmp_path / "Downloads").mkdir()
        (tmp_path / "Desktop").mkdir()

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.chdir(tmp_path)
        assert _resolve_path("ghost.svs") is None


class TestResolvePathEdgeCases:
    """Edge cases: spaces, special characters, relative with slashes."""

    def test_path_with_spaces(self, tmp_path):
        """Paths containing spaces are resolved correctly."""
        spaced = tmp_path / "my slides" / "test slide.svs"
        spaced.parent.mkdir(parents=True)
        spaced.write_bytes(b"FAKE")
        assert _resolve_path(str(spaced)) == str(spaced)

    def test_relative_path_with_slash_not_searched(self, tmp_path, monkeypatch):
        """A relative path containing '/' is NOT treated as a bare filename."""
        # Even though Downloads/slide.svs exists, the path "subdir/slide.svs"
        # should not match it because it contains a slash.
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "slide.svs").write_bytes(b"FAKE")

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        # "subdir/slide.svs" has a slash → _resolve_path should NOT search common dirs
        assert _resolve_path("subdir/slide.svs") is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert _resolve_path("") is None
