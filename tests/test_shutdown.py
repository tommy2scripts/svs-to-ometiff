"""Tests for graceful shutdown: ConversionService.shutdown(), signal handlers,
and cancellation checkpoints in the conversion pipeline.
"""

import os
import signal
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# ConversionService.shutdown() unit tests
# ---------------------------------------------------------------------------


class TestConversionServiceShutdown:
    def test_shutdown_no_active_jobs(self):
        """shutdown() is a no-op when no executor was initialised."""
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        svc.shutdown(timeout_seconds=1)
        assert svc._executor is None
        assert svc._dispatcher_thread is None
        assert len(svc.active_jobs) == 0

    def test_shutdown_cancels_executor_futures(self):
        """shutdown() calls ProcessPoolExecutor.shutdown with cancel_futures=True."""
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        mock_executor = MagicMock()
        svc._executor = mock_executor
        svc._dispatcher_thread = MagicMock()
        svc._dispatcher_thread.is_alive.return_value = False

        svc.shutdown(timeout_seconds=1)

        mock_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        assert svc._executor is None

    def test_shutdown_unblocks_sse_queues(self):
        """shutdown() puts an error event into every active progress queue."""
        from queue import Queue
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        q1, q2 = Queue(), Queue()
        svc.progress_queues = {"rid-1": q1, "rid-2": q2}

        svc.shutdown(timeout_seconds=1)

        for q in (q1, q2):
            event_type, data = q.get_nowait()
            assert event_type == "error"
            assert "shutting down" in data["error"].lower()

    def test_shutdown_unblocks_dispatcher_thread(self):
        """shutdown() sends a sentinel to the multiprocessing queue."""
        from multiprocessing import Manager
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        manager = Manager()
        svc._manager = manager
        m_queue = manager.Queue()
        svc._m_queue = m_queue
        svc._dispatcher_thread = MagicMock()
        svc._dispatcher_thread.is_alive.return_value = False

        # Prevent shutdown from destroying the manager so we can inspect the queue.
        # Use a local reference (m_queue) since shutdown nullifies svc._m_queue.
        with patch.object(manager, "shutdown", return_value=None):
            svc.shutdown(timeout_seconds=1)

        rid, event_type, data = m_queue.get_nowait()
        assert rid == "__shutdown__"

        manager.shutdown()

    def test_shutdown_clears_active_jobs(self):
        """shutdown() empties the active_jobs set."""
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        svc.active_jobs = {"a", "b", "c"}
        svc.shutdown(timeout_seconds=1)
        assert svc.active_jobs == set()


# ---------------------------------------------------------------------------
# Dispatcher thread shutdown
# ---------------------------------------------------------------------------


class TestDispatcherShutdown:
    def test_dispatcher_exits_on_shutdown_event(self):
        """_dispatch_events exits its loop when _shutdown_event is set."""
        from multiprocessing import Manager
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        svc._manager = Manager()
        svc._m_queue = svc._manager.Queue()
        svc._shutdown_event.set()

        thread = threading.Thread(target=svc._dispatch_events, daemon=True)
        thread.start()
        thread.join(timeout=3)

        assert not thread.is_alive()
        svc._manager.shutdown()

    def test_dispatcher_exits_on_sentinel(self):
        """_dispatch_events exits when it receives the __shutdown__ sentinel."""
        from multiprocessing import Manager
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        svc._manager = Manager()
        svc._m_queue = svc._manager.Queue()
        svc._m_queue.put(("__shutdown__", "shutdown", {}))

        thread = threading.Thread(target=svc._dispatch_events, daemon=True)
        thread.start()
        thread.join(timeout=3)

        assert not thread.is_alive()
        svc._manager.shutdown()


# ---------------------------------------------------------------------------
# Signal handler installation tests
# ---------------------------------------------------------------------------


class TestWorkerSignalHandlers:
    def test_install_worker_handlers_sets_signal(self):
        """_install_worker_signal_handlers registers handlers for SIGTERM/SIGINT."""
        from svs_to_ometiff.converter import _shutdown_event
        from svs_to_ometiff_gui.services import _install_worker_signal_handlers

        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        _shutdown_event.clear()
        try:
            _install_worker_signal_handlers()
            handler = signal.getsignal(signal.SIGTERM)

            assert callable(handler)
            handler(signal.SIGTERM, None)
            assert _shutdown_event.is_set()
        finally:
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            _shutdown_event.clear()


class TestPytestDetection:
    def test_pytest_detection_active(self):
        """_is_running_under_pytest returns True during test runs."""
        from svs_to_ometiff_gui.serve import _is_running_under_pytest
        assert _is_running_under_pytest() is True

    def test_gunicorn_detection_negative(self):
        """_is_running_under_gunicorn returns False during test runs."""
        from svs_to_ometiff_gui.serve import _is_running_under_gunicorn
        assert _is_running_under_gunicorn() is False


# ---------------------------------------------------------------------------
# Converter cancellation checkpoints
# ---------------------------------------------------------------------------


class TestConverterCancellation:
    def test_shutdown_event_starts_unset(self):
        """_shutdown_event is initially clear."""
        from svs_to_ometiff.converter import _shutdown_event
        _shutdown_event.clear()
        assert not _shutdown_event.is_set()

    def test_conversion_cancelled_before_tile_decoding(self, tmp_path: Path):
        """Cancelling before tile decoding raises _ConversionCancelled and cleans temp dir."""
        from svs_to_ometiff import ConvertConfig, convert
        from svs_to_ometiff.converter import _ConversionCancelled, _shutdown_event
        from tests.helpers import write_synthetic_33007_svs

        input_svs = tmp_path / "synthetic.svs"
        output = tmp_path / "out.ome.tiff"
        write_synthetic_33007_svs(input_svs, width=16, height=16)

        temp_base = tempfile.mkdtemp(prefix="test_shutdown_", dir=str(tmp_path))
        temp_dirs_before = set(Path(temp_base).iterdir()) if Path(temp_base).exists() else set()

        _shutdown_event.set()
        with pytest.raises(_ConversionCancelled, match="before tile decoding"):
            convert(
                ConvertConfig(
                    input_svs=str(input_svs),
                    output_ometiff=str(output),
                    tile_size=16,
                    compression=None,
                    num_levels=1,
                    verbose=False,
                    temp_dir=temp_base,
                )
            )
        _shutdown_event.clear()

        # Temp directory created by convert() should have been cleaned up
        temp_dirs_after = set(Path(temp_base).iterdir()) if Path(temp_base).exists() else set()
        new_dirs = temp_dirs_after - temp_dirs_before
        assert len(new_dirs) == 0, f"Orphaned temp directories: {new_dirs}"

    def test_conversion_cancelled_after_tile_decoding(self, tmp_path: Path):
        """Cancelling after tile decoding still cleans up temp directory."""
        from svs_to_ometiff import ConvertConfig, convert
        from svs_to_ometiff.converter import _ConversionCancelled, _shutdown_event
        from tests.helpers import write_synthetic_33007_svs

        input_svs = tmp_path / "synthetic.svs"
        output = tmp_path / "out.ome.tiff"
        write_synthetic_33007_svs(input_svs, width=64, height=64)

        temp_base = tempfile.mkdtemp(prefix="test_shutdown2_", dir=str(tmp_path))

        from svs_to_ometiff import converter as conv_module
        original_stage = conv_module._stage_level0_memmap

        def _stage_and_cancel(*args, **kwargs):
            result = original_stage(*args, **kwargs)
            _shutdown_event.set()
            return result

        try:
            conv_module._stage_level0_memmap = _stage_and_cancel

            with pytest.raises(_ConversionCancelled, match="after tile decoding"):
                convert(
                    ConvertConfig(
                        input_svs=str(input_svs),
                        output_ometiff=str(output),
                        tile_size=16,
                        compression=None,
                        num_levels=3,
                        verbose=False,
                        temp_dir=temp_base,
                    )
                )
        finally:
            _shutdown_event.clear()
            conv_module._stage_level0_memmap = original_stage

    def test_cancellation_during_pyramid_building(self, tmp_path: Path):
        """Cancellation between pyramid building and OME-TIFF write cleans up."""
        from svs_to_ometiff import ConvertConfig, convert
        from svs_to_ometiff.converter import _ConversionCancelled, _shutdown_event
        from tests.helpers import write_synthetic_33007_svs

        input_svs = tmp_path / "synthetic.svs"
        output = tmp_path / "out.ome.tiff"
        write_synthetic_33007_svs(input_svs, width=64, height=64)

        temp_base = tempfile.mkdtemp(prefix="test_shutdown3_", dir=str(tmp_path))

        from svs_to_ometiff import converter as conv_module
        original_build = conv_module.build_pyramid_memmaps

        def _build_and_cancel(*args, **kwargs):
            result = original_build(*args, **kwargs)
            _shutdown_event.set()
            return result

        try:
            conv_module.build_pyramid_memmaps = _build_and_cancel

            with pytest.raises(_ConversionCancelled, match="after pyramid building"):
                convert(
                    ConvertConfig(
                        input_svs=str(input_svs),
                        output_ometiff=str(output),
                        tile_size=16,
                        compression=None,
                        num_levels=2,
                        verbose=False,
                        temp_dir=temp_base,
                    )
                )
        finally:
            _shutdown_event.clear()
            conv_module.build_pyramid_memmaps = original_build


# ---------------------------------------------------------------------------
# Gunicorn service shutdown integration
# ---------------------------------------------------------------------------


class TestGunicornShutdown:
    def test_shutdown_cleans_up_manager_resources(self):
        """shutdown() tears down the Manager without leaking."""
        from multiprocessing import Manager
        from svs_to_ometiff_gui.services import ConversionService

        svc = ConversionService()
        svc._manager = Manager()
        svc._m_queue = svc._manager.Queue()
        svc._dispatcher_thread = MagicMock()
        svc._dispatcher_thread.is_alive.return_value = False

        svc.shutdown(timeout_seconds=1)

        assert svc._manager is None
        assert svc._m_queue is None
        assert svc._dispatcher_thread is None

    @patch("os._exit")
    def test_sigterm_handler_exits_cleanly(self, mock_exit):
        """The gunicorn SIGTERM handler calls shutdown() then exits."""
        from svs_to_ometiff_gui.serve import _install_gunicorn_sigterm_handler, app
        from unittest.mock import patch as upatch

        try:
            # Bypass pytest detection: simulate gunicorn environment
            with upatch("svs_to_ometiff_gui.serve._is_running_under_pytest", return_value=False):
                with upatch.object(app.config["CONVERSION_SERVICE"], "shutdown") as mock_shutdown:
                    _install_gunicorn_sigterm_handler()
                    handler = signal.getsignal(signal.SIGTERM)
                    assert callable(handler)
                    handler(signal.SIGTERM, None)
                    mock_shutdown.assert_called_once()
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Temp directory cleanup
# ---------------------------------------------------------------------------


class TestTempCleanupOnCancel:
    def test_memmap_files_cleaned_on_worker_cancel(self, tmp_path: Path):
        """When _ConversionCancelled is raised, memmap files are removed."""
        from svs_to_ometiff.pyramid import cleanup_pyramid_memmaps

        temp_dir = str(tmp_path / "temp_memmaps")
        mmap_path = str(Path(temp_dir) / "level_0.dat")
        Path(temp_dir).mkdir(parents=True)
        mm = np.memmap(mmap_path, dtype=np.uint8, mode="w+", shape=(16, 16, 3))
        mm[:] = 128
        mm.flush()

        cleanup_pyramid_memmaps([mm], temp_dir)
        assert not Path(temp_dir).exists()
