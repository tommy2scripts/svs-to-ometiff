"""Tests for Windows-safe temp directory cleanup behavior.

These tests verify that cleanup failures after a successful write are handled
gracefully — the conversion is marked complete with a warning rather than an error.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from svs_to_ometiff.pyramid import (
    close_memmap_array,
    cleanup_pyramid_memmaps,
)

# ---------------------------------------------------------------------------
# cleanup_pyramid_memmaps unit tests
# ---------------------------------------------------------------------------


class TestCleanupPyramidMemmaps:
    def test_close_memmap_array_tolerates_regular_ndarray(self) -> None:
        """The canonical close helper is a no-op for regular ndarrays."""
        close_memmap_array(np.zeros((2, 2, 3), dtype=np.uint8))

    def test_cleanup_normal(self, tmp_path: Path) -> None:
        """Normal cleanup: memmaps closed, temp dir removed."""
        temp_dir = str(tmp_path / "temp_memmaps")
        Path(temp_dir).mkdir(parents=True)
        mmap_path = str(Path(temp_dir) / "test.dat")
        m = np.memmap(mmap_path, dtype=np.uint8, mode="w+", shape=(16, 16, 3))
        m[:] = 1
        m.flush()
        levels = [m]

        result = cleanup_pyramid_memmaps(levels, temp_dir)
        assert result is None  # no warning
        assert not Path(temp_dir).exists()

    def test_cleanup_no_memmaps(self, tmp_path: Path) -> None:
        """Cleanup with regular arrays (no memmaps) succeeds."""
        temp_dir = str(tmp_path / "empty_temp")
        Path(temp_dir).mkdir(parents=True)
        levels = [np.zeros((16, 16, 3), dtype=np.uint8)]

        result = cleanup_pyramid_memmaps(levels, temp_dir)
        assert result is None
        assert not Path(temp_dir).exists()

    def test_cleanup_already_gone(self, tmp_path: Path) -> None:
        """Cleanup when temp dir is already removed succeeds silently."""
        temp_dir = str(tmp_path / "already_gone")
        Path(temp_dir).mkdir(parents=True)
        levels: list = []

        # Remove the dir ourselves first
        shutil.rmtree(temp_dir)

        result = cleanup_pyramid_memmaps(levels, temp_dir)
        assert result is None  # No warning for already-removed dir

    def test_cleanup_retry_eventually_succeeds(self, tmp_path: Path) -> None:
        """Cleanup with intermittent PermissionError retries and eventually succeeds."""
        temp_dir = str(tmp_path / "retry_temp")
        Path(temp_dir).mkdir(parents=True)

        fail_count = [0]

        original_rmtree = shutil.rmtree

        def _failing_rmtree(path, *a, **kw):
            fail_count[0] += 1
            if fail_count[0] <= 2:
                raise PermissionError(f"Cannot delete {path}: file in use")
            return original_rmtree(path, *a, **kw)

        levels: list = []
        with patch("shutil.rmtree", _failing_rmtree):
            result = cleanup_pyramid_memmaps(levels, temp_dir, max_retries=3)

        assert result is None
        assert not Path(temp_dir).exists()
        assert fail_count[0] == 3  # 2 failures + 1 success

    def test_cleanup_retry_exhausted_returns_warning(self, tmp_path: Path) -> None:
        """Cleanup that always fails returns a warning string, not None."""
        temp_dir = str(tmp_path / "stuck_temp")
        Path(temp_dir).mkdir(parents=True)

        def _always_failing_rmtree(path, *a, **kw):
            raise PermissionError(f"Cannot delete {path}: locked by another process")

        levels: list = []
        with patch("shutil.rmtree", _always_failing_rmtree):
            result = cleanup_pyramid_memmaps(levels, temp_dir, max_retries=2)

        assert result is not None
        assert "cleanup failed" in result.lower()
        assert Path(temp_dir).exists()  # Dir still there

        # Cleanup the test dir
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression: cleanup failure after successful write (converter behavior)
# ---------------------------------------------------------------------------

class TestCleanupFailureOnWriteSuccess:
    """Verify that the converter handles cleanup failure gracefully.

    When the OME-TIFF is written successfully but temp cleanup fails, the
    conversion should be considered complete (not failed) with a warning.
    """

    def test_cleanup_warning_in_result_dict(self) -> None:
        """A cleanup warning should be a string, not an error."""
        # This tests the contract: cleanup_pyramid_memmaps returns
        # a string on failure, not raising an exception
        temp_dir = tempfile.mkdtemp()
        levels = [np.zeros((16, 16, 3), dtype=np.uint8)]

        # Make cleanup fail by creating a locked file
        locked_file = Path(temp_dir) / "locked.dat"
        locked_file.write_bytes(b"LOCKED")

        with patch("shutil.rmtree") as mock_rmtree:
            mock_rmtree.side_effect = PermissionError(
                f"Cannot delete {temp_dir}: file in use"
            )
            result = cleanup_pyramid_memmaps(levels, str(temp_dir), max_retries=1)

        assert result is not None
        assert isinstance(result, str)
        assert "cleanup failed" in result.lower()

        # Cleanup
        import stat
        locked_file.chmod(stat.S_IWUSR | stat.S_IWGRP)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_convert_returns_cleanup_warning_after_success(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Successful writes stay successful when only temp cleanup fails."""
        from svs_to_ometiff import converter
        from svs_to_ometiff.config import ConvertConfig

        input_svs = tmp_path / "slide.svs"
        output = tmp_path / "slide.ome.tiff"
        temp_root = tmp_path / "temp_root"
        input_svs.write_bytes(b"not used")

        monkeypatch.setattr(
            converter,
            "read_svs_metadata",
            lambda _path: {
                "compression": 33007,
                "width": 16,
                "height": 16,
                "src_tile_width": 16,
                "src_tile_height": 16,
                "tile_count": 1,
                "mpp": 0.5,
                "magnification": 20,
            },
        )

        captured_temp_dirs = []

        def fake_stage(_config, _metadata, temp_dir):
            captured_temp_dirs.append(temp_dir)
            return np.zeros((16, 16, 3), dtype=np.uint8)

        def fake_write(path, *_args, **_kwargs):
            Path(path).write_bytes(b"ome")

        monkeypatch.setattr(converter, "_stage_level0_memmap", fake_stage)
        monkeypatch.setattr(
            converter,
            "build_pyramid_memmaps",
            lambda level0, *_args, **_kwargs: [level0],
        )
        monkeypatch.setattr(converter, "write_pyramidal_ometiff", fake_write)
        monkeypatch.setattr(
            converter,
            "_cleanup_pyramid_memmaps",
            lambda _levels, temp_dir: f"cleanup failed: {temp_dir}",
        )

        result = converter.convert(
            ConvertConfig(
                input_svs=str(input_svs),
                output_ometiff=str(output),
                temp_dir=str(temp_root),
                verbose=False,
            )
        )

        assert output.exists()
        assert result["cleanup_warning"].startswith("cleanup failed:")
        assert captured_temp_dirs
        assert Path(captured_temp_dirs[0]).parent == temp_root

    def test_convert_preserves_original_error_when_write_fails(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Cleanup after failed writes must not mask the write exception."""
        from svs_to_ometiff import converter
        from svs_to_ometiff.config import ConvertConfig

        input_svs = tmp_path / "slide.svs"
        output = tmp_path / "slide.ome.tiff"
        input_svs.write_bytes(b"not used")

        monkeypatch.setattr(
            converter,
            "read_svs_metadata",
            lambda _path: {
                "compression": 33007,
                "width": 16,
                "height": 16,
                "src_tile_width": 16,
                "src_tile_height": 16,
                "tile_count": 1,
                "mpp": 0.5,
                "magnification": None,
            },
        )
        monkeypatch.setattr(
            converter,
            "_stage_level0_memmap",
            lambda *_args: np.zeros((16, 16, 3), dtype=np.uint8),
        )
        monkeypatch.setattr(
            converter,
            "build_pyramid_memmaps",
            lambda level0, *_args, **_kwargs: [level0],
        )
        monkeypatch.setattr(
            converter,
            "write_pyramidal_ometiff",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("write failed")),
        )
        monkeypatch.setattr(
            converter,
            "_cleanup_pyramid_memmaps",
            lambda _levels, _temp_dir: "cleanup failed too",
        )

        try:
            converter.convert(
                ConvertConfig(
                    input_svs=str(input_svs),
                    output_ometiff=str(output),
                    verbose=False,
                )
            )
        except RuntimeError as exc:
            assert str(exc) == "write failed"
        else:
            raise AssertionError("convert should have raised the write failure")


class TestTempDirConfig:
    """Tests for the configurable temp directory feature."""

    def test_temp_dir_in_convert_config(self) -> None:
        """ConvertConfig accepts a temp_dir parameter."""
        from svs_to_ometiff.config import ConvertConfig

        config = ConvertConfig(
            input_svs="/tmp/test.svs",
            output_ometiff="/tmp/test.ome.tiff",
            temp_dir="/tmp/svs_temp",
            tile_size=1024,
        )
        assert config.temp_dir == "/tmp/svs_temp"

    def test_temp_dir_default_none(self) -> None:
        """ConvertConfig temp_dir defaults to None (system temp)."""
        from svs_to_ometiff.config import ConvertConfig

        config = ConvertConfig(
            input_svs="/tmp/test.svs",
            output_ometiff="/tmp/test.ome.tiff",
        )
        assert config.temp_dir is None
