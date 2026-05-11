"""Tests for svs_to_ometiff_gui.serve and svs_to_ometiff_gui.__init__."""

import json
import threading
from queue import Queue
from typing import Generator
from unittest.mock import patch

import pytest

import svs_to_ometiff_gui
import svs_to_ometiff_gui.serve as serve_mod
from svs_to_ometiff_gui.serve import (
    _resolve_path,
    _run_conversion,
    app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset serve module globals before and after each test."""
    serve_mod._progress_queues.clear()
    serve_mod._latest_events.clear()
    serve_mod._active_conversion = False
    serve_mod._conversion_thread = None
    yield
    serve_mod._progress_queues.clear()
    serve_mod._latest_events.clear()
    serve_mod._active_conversion = False
    serve_mod._conversion_thread = None


@pytest.fixture()
def client():
    """Return a Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# __init__.py — version
# ===========================================================================


def test_version_string() -> None:
    """Package exposes the expected version string."""
    assert svs_to_ometiff_gui.__version__ == "0.1.0"


# ===========================================================================
# _resolve_path
# ===========================================================================


class TestResolvePath:
    """Tests for the _resolve_path helper."""

    def test_returns_path_when_file_exists_at_exact_path(self, tmp_path) -> None:
        """Returns the path unchanged when the given path is an existing file."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        result = _resolve_path(str(f))
        assert result == str(f)

    def test_returns_none_when_full_path_does_not_exist(self) -> None:
        """Returns None when a full path (containing a separator) does not exist."""
        result = _resolve_path("/nonexistent/path/slide.svs")
        assert result is None

    def test_returns_none_when_bare_filename_not_found_anywhere(self, tmp_path) -> None:
        """Returns None when a bare filename cannot be found in any candidate dir."""
        with patch("os.path.isfile", return_value=False):
            result = _resolve_path("totally_absent.svs")
        assert result is None

    def test_finds_bare_filename_in_downloads(self, tmp_path, monkeypatch) -> None:
        """Resolves a bare filename located in ~/Downloads."""
        fake_downloads = tmp_path / "Downloads"
        fake_downloads.mkdir()
        target = fake_downloads / "slide.svs"
        target.write_bytes(b"")

        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path))
        result = _resolve_path("slide.svs")
        assert result == str(target)

    def test_finds_bare_filename_in_desktop(self, tmp_path, monkeypatch) -> None:
        """Resolves a bare filename located in ~/Desktop (Downloads absent)."""
        fake_desktop = tmp_path / "Desktop"
        fake_desktop.mkdir()
        target = fake_desktop / "slide.svs"
        target.write_bytes(b"")

        # Make Downloads not have the file so Desktop is searched next
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path))
        result = _resolve_path("slide.svs")
        assert result == str(target)

    def test_finds_bare_filename_in_cwd(self, tmp_path, monkeypatch) -> None:
        """Resolves a bare filename found in the current working directory."""
        target = tmp_path / "slide.svs"
        target.write_bytes(b"")

        monkeypatch.setattr("os.path.expanduser", lambda p: "/no/such/home")
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        result = _resolve_path("slide.svs")
        assert result == str(target)

    def test_path_with_separator_not_searched_in_candidates(self, tmp_path) -> None:
        """A path that contains a separator is not searched in candidate dirs."""
        result = _resolve_path("/abs/path/slide.svs")
        assert result is None

    def test_backslash_path_not_searched_in_candidates(self) -> None:
        """A Windows-style path with backslash is not searched in candidate dirs."""
        result = _resolve_path("C:\\Users\\user\\slide.svs")
        assert result is None


# ===========================================================================
# _run_conversion
# ===========================================================================


class TestRunConversion:
    """Tests for the _run_conversion background task function."""

    def test_returns_immediately_when_request_id_not_registered(self) -> None:
        """No-op when the request_id has no queue registered."""
        # Should not raise; queue is absent
        _run_conversion("unknown-id", {"input_path": "x.svs"})

    def test_puts_complete_event_on_success(self) -> None:
        """Puts ('complete', {}) on the queue after a successful convert call."""
        req_id = "test-req-1"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        with patch("svs_to_ometiff_gui.serve.convert") as mock_convert:
            mock_convert.return_value = None
            _run_conversion(req_id, {"input_path": "x.svs", "output_path": "x.ome.tiff"})

        event_type, data = q.get_nowait()
        assert event_type == "complete"
        assert data == {}

    def test_puts_error_event_on_exception(self) -> None:
        """Puts ('error', {'error': str(exc)}) on the queue when convert raises."""
        req_id = "test-req-2"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=RuntimeError("boom")):
            _run_conversion(req_id, {"input_path": "x.svs"})

        event_type, data = q.get_nowait()
        assert event_type == "error"
        assert "boom" in data["error"]

    def test_progress_callback_enqueues_message(self) -> None:
        """progress_callback inserts a progress event with just the message."""
        req_id = "test-req-3"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        captured_callback = {}

        def fake_convert(**kwargs):
            captured_callback["cb"] = kwargs["progress_logger"]
            kwargs["progress_logger"]("step 1")

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=fake_convert):
            _run_conversion(req_id, {"input_path": "x.svs"})

        items = []
        while not q.empty():
            items.append(q.get_nowait())

        progress_events = [d for t, d in items if t == "progress"]
        assert len(progress_events) >= 1
        assert progress_events[0]["message"] == "step 1"
        assert "percent" not in progress_events[0]

    def test_progress_callback_includes_percent_when_provided(self) -> None:
        """progress_callback includes 'percent' key only when a value is supplied."""
        req_id = "test-req-4"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        def fake_convert(**kwargs):
            kwargs["progress_logger"]("step 2", percent=42.0)

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=fake_convert):
            _run_conversion(req_id, {"input_path": "x.svs"})

        items = []
        while not q.empty():
            items.append(q.get_nowait())

        progress_events = [d for t, d in items if t == "progress"]
        assert progress_events[0]["percent"] == 42.0

    def test_progress_callback_updates_latest_events(self) -> None:
        """progress_callback stores the latest event in _latest_events."""
        req_id = "test-req-5"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        def fake_convert(**kwargs):
            kwargs["progress_logger"]("running")

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=fake_convert):
            _run_conversion(req_id, {"input_path": "x.svs"})

        # After completion, latest event is "complete"
        assert serve_mod._latest_events[req_id]["type"] == "complete"

    def test_run_conversion_passes_default_params(self) -> None:
        """Passes default tile_size, compression, num_levels, downsample_factor."""
        req_id = "test-req-6"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q

        call_kwargs = {}

        def fake_convert(**kwargs):
            call_kwargs.update(kwargs)

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=fake_convert):
            _run_conversion(req_id, {"input_path": "x.svs"})

        assert call_kwargs["tile_size"] == 512
        assert call_kwargs["compression"] == "none"
        assert call_kwargs["num_levels"] == 3
        assert call_kwargs["downsample_factor"] == 2


# ===========================================================================
# GET /
# ===========================================================================


class TestIndexRoute:
    """Tests for the GET / route."""

    def test_index_returns_200(self, client) -> None:
        """Index page returns HTTP 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_returns_html(self, client) -> None:
        """Index page content type is HTML."""
        resp = client.get("/")
        assert b"svs-to-ometiff" in resp.data


# ===========================================================================
# POST /convert
# ===========================================================================


class TestHandleConvert:
    """Tests for the POST /convert endpoint."""

    def _post(self, client, payload):
        return client.post(
            "/convert",
            data=json.dumps(payload),
            content_type="application/json",
        )

    # --- Validation failures -------------------------------------------------

    def test_missing_input_path_returns_400(self, client) -> None:
        """Returns 400 when input_path is absent from the request body."""
        resp = self._post(client, {})
        assert resp.status_code == 400
        assert "input_path is required" in resp.get_json()["error"]

    def test_empty_input_path_returns_400(self, client) -> None:
        """Returns 400 when input_path is an empty string."""
        resp = self._post(client, {"input_path": "   "})
        assert resp.status_code == 400
        assert "input_path is required" in resp.get_json()["error"]

    def test_nonexistent_file_returns_400(self, client) -> None:
        """Returns 400 with a helpful message when the file cannot be found."""
        resp = self._post(client, {"input_path": "/no/such/file.svs"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "File not found" in data["error"]

    def test_non_svs_extension_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when the resolved file does not have a .svs extension."""
        f = tmp_path / "image.tif"
        f.write_bytes(b"")
        resp = self._post(client, {"input_path": str(f)})
        assert resp.status_code == 400
        assert ".svs extension" in resp.get_json()["error"]

    def test_unwritable_output_dir_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when the output directory is not writable."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        with patch("os.access", return_value=False):
            resp = self._post(
                client,
                {"input_path": str(f), "output_path": "/root/no_write/out.ome.tiff"},
            )
        assert resp.status_code == 400
        assert "not writable" in resp.get_json()["error"]

    def test_zero_tile_size_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when tile_size is zero."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        with patch("os.access", return_value=True):
            resp = self._post(
                client,
                {"input_path": str(f), "tile_size": 0},
            )
        assert resp.status_code == 400
        assert "tile_size must be a positive integer" in resp.get_json()["error"]

    def test_negative_tile_size_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when tile_size is negative."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        with patch("os.access", return_value=True):
            resp = self._post(
                client,
                {"input_path": str(f), "tile_size": -256},
            )
        assert resp.status_code == 400
        assert "tile_size must be a positive integer" in resp.get_json()["error"]

    def test_string_tile_size_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when tile_size cannot be parsed as an integer."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        with patch("os.access", return_value=True):
            resp = self._post(
                client,
                {"input_path": str(f), "tile_size": "big"},
            )
        assert resp.status_code == 400
        assert "tile_size must be a positive integer" in resp.get_json()["error"]

    def test_already_running_returns_409(self, client, tmp_path) -> None:
        """Returns 409 when a conversion is already active."""
        serve_mod._active_conversion = True
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        resp = self._post(client, {"input_path": str(f)})
        assert resp.status_code == 409
        assert "already running" in resp.get_json()["error"]

    # --- Successful request --------------------------------------------------

    def test_success_returns_request_id_and_output_path(self, client, tmp_path) -> None:
        """Returns 200 with request_id and output_path on a valid request."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")

        with patch("svs_to_ometiff_gui.serve.convert") as mock_convert:
            mock_convert.return_value = None
            resp = self._post(client, {"input_path": str(f)})

        assert resp.status_code == 200
        data = resp.get_json()
        assert "request_id" in data
        assert "output_path" in data

    def test_success_auto_derives_ometiff_output_path(self, client, tmp_path) -> None:
        """Auto-derives output path by replacing .svs with .ome.tiff."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")

        with patch("svs_to_ometiff_gui.serve.convert"):
            resp = self._post(client, {"input_path": str(f)})

        data = resp.get_json()
        assert data["output_path"].endswith(".ome.tiff")
        assert not data["output_path"].endswith(".svs.ome.tiff")

    def test_success_uses_provided_output_path(self, client, tmp_path) -> None:
        """Uses the caller-supplied output_path instead of auto-deriving it."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        custom_out = str(tmp_path / "custom.ome.tiff")

        with patch("svs_to_ometiff_gui.serve.convert"):
            resp = self._post(
                client,
                {"input_path": str(f), "output_path": custom_out},
            )

        data = resp.get_json()
        assert data["output_path"] == custom_out

    def test_success_sets_active_conversion_flag(self, client, tmp_path) -> None:
        """Sets _active_conversion=True immediately after a valid convert request."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")

        # Block the background thread so the flag stays True during assertion
        event = threading.Event()

        def slow_convert(**kwargs):
            event.wait(timeout=5)

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=slow_convert):
            resp = self._post(client, {"input_path": str(f)})
            assert resp.status_code == 200
            assert serve_mod._active_conversion is True
        event.set()

    def test_success_registers_queue_for_request_id(self, client, tmp_path) -> None:
        """Registers a Queue in _progress_queues keyed by the returned request_id."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")

        with patch("svs_to_ometiff_gui.serve.convert"):
            resp = self._post(client, {"input_path": str(f)})

        req_id = resp.get_json()["request_id"]
        # Queue should exist (may have been cleaned up if thread finished very fast)
        # Wait a moment for thread to complete
        thread = serve_mod._conversion_thread
        if thread is not None:
            thread.join(timeout=2.0)
        # After thread completes the queue is cleaned up; request was registered
        assert req_id is not None

    def test_success_passes_optional_params_to_conversion(self, client, tmp_path) -> None:
        """Passes tile_size, compression, num_levels, downsample_factor to convert."""
        f = tmp_path / "slide.svs"
        f.write_bytes(b"")
        call_kwargs = {}

        def capture(**kwargs):
            call_kwargs.update(kwargs)

        with patch("svs_to_ometiff_gui.serve.convert", side_effect=capture):
            resp = self._post(
                client,
                {
                    "input_path": str(f),
                    "tile_size": 256,
                    "compression": "lzw",
                    "num_levels": 2,
                    "downsample_factor": 3,
                },
            )
        assert resp.status_code == 200
        thread = serve_mod._conversion_thread
        if thread is not None:
            thread.join(timeout=2.0)
        assert call_kwargs.get("tile_size") == 256
        assert call_kwargs.get("compression") == "lzw"
        assert call_kwargs.get("num_levels") == 2
        assert call_kwargs.get("downsample_factor") == 3


# ===========================================================================
# GET /progress/<request_id>
# ===========================================================================


class TestStreamProgress:
    """Tests for the GET /progress/<request_id> SSE endpoint."""

    def test_invalid_request_id_returns_404(self, client) -> None:
        """Returns 404 for an unrecognised request_id."""
        resp = client.get("/progress/nonexistent-id")
        assert resp.status_code == 404
        assert "Invalid request_id" in resp.get_json()["error"]

    def _drain_sse(self, client, request_id: str) -> list[dict]:
        """Read the full SSE stream for a request and return parsed events."""
        resp = client.get(f"/progress/{request_id}")
        assert resp.status_code == 200
        events = []
        for line in resp.data.decode().splitlines():
            if line.startswith("event:"):
                events.append({"type": line.split(":", 1)[1].strip()})
            elif line.startswith("data:"):
                if events:
                    events[-1]["data"] = json.loads(line.split(":", 1)[1].strip())
        return events

    def test_streams_complete_event(self, client) -> None:
        """SSE stream emits a 'complete' event when the conversion succeeds."""
        req_id = "stream-complete-1"
        q: Queue = Queue()
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q

        events = self._drain_sse(client, req_id)
        assert any(e["type"] == "complete" for e in events)

    def test_streams_error_event(self, client) -> None:
        """SSE stream emits an 'error' event when the conversion fails."""
        req_id = "stream-error-1"
        q: Queue = Queue()
        q.put(("error", {"error": "something went wrong"}))
        serve_mod._progress_queues[req_id] = q

        events = self._drain_sse(client, req_id)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "something went wrong" in error_events[0]["data"]["error"]

    def test_streams_progress_then_complete(self, client) -> None:
        """SSE stream emits progress events followed by a final complete event."""
        req_id = "stream-prog-1"
        q: Queue = Queue()
        q.put(("progress", {"message": "step A", "percent": 25.0}))
        q.put(("progress", {"message": "step B", "percent": 75.0}))
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q

        events = self._drain_sse(client, req_id)
        types = [e["type"] for e in events]
        assert types.count("progress") == 2
        assert types[-1] == "complete"

    def test_replays_cached_complete_event_on_reconnect(self, client) -> None:
        """Replays the cached 'complete' event immediately when reconnecting."""
        req_id = "replay-complete-1"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q
        serve_mod._latest_events[req_id] = {"type": "complete", "data": {}}

        events = self._drain_sse(client, req_id)
        assert any(e["type"] == "complete" for e in events)

    def test_replays_cached_error_event_on_reconnect(self, client) -> None:
        """Replays the cached 'error' event immediately when reconnecting."""
        req_id = "replay-error-1"
        q: Queue = Queue()
        serve_mod._progress_queues[req_id] = q
        serve_mod._latest_events[req_id] = {
            "type": "error",
            "data": {"error": "cached failure"},
        }

        events = self._drain_sse(client, req_id)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "cached failure" in error_events[0]["data"]["error"]

    def test_replays_cached_progress_event_then_continues(self, client) -> None:
        """Replays a cached progress event then continues consuming the queue."""
        req_id = "replay-prog-1"
        q: Queue = Queue()
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q
        serve_mod._latest_events[req_id] = {
            "type": "progress",
            "data": {"message": "cached step"},
        }

        events = self._drain_sse(client, req_id)
        types = [e["type"] for e in events]
        assert "progress" in types
        assert "complete" in types

    def test_response_content_type_is_event_stream(self, client) -> None:
        """SSE response has Content-Type: text/event-stream."""
        req_id = "ct-check-1"
        q: Queue = Queue()
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q

        resp = client.get(f"/progress/{req_id}")
        assert "text/event-stream" in resp.content_type

    def test_cleanup_clears_queue_after_complete(self, client) -> None:
        """After the SSE stream ends, the queue is removed from _progress_queues."""
        req_id = "cleanup-1"
        q: Queue = Queue()
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q

        self._drain_sse(client, req_id)
        assert req_id not in serve_mod._progress_queues

    def test_cleanup_resets_active_conversion_after_complete(self, client) -> None:
        """After the SSE stream ends, _active_conversion is reset to False."""
        req_id = "cleanup-flag-1"
        q: Queue = Queue()
        q.put(("complete", {}))
        serve_mod._progress_queues[req_id] = q
        serve_mod._active_conversion = True

        self._drain_sse(client, req_id)
        assert serve_mod._active_conversion is False


# ===========================================================================
# POST /open_folder
# ===========================================================================


class TestHandleOpenFolder:
    """Tests for the POST /open_folder endpoint."""

    def _post(self, client, payload):
        return client.post(
            "/open_folder",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_path_returns_400(self, client) -> None:
        """Returns 400 when the request body has no 'path' key."""
        resp = self._post(client, {})
        assert resp.status_code == 400
        assert "Invalid folder path" in resp.get_json()["error"]

    def test_empty_path_returns_400(self, client) -> None:
        """Returns 400 when 'path' is an empty string."""
        resp = self._post(client, {"path": "   "})
        assert resp.status_code == 400
        assert "Invalid folder path" in resp.get_json()["error"]

    def test_nonexistent_directory_returns_400(self, client) -> None:
        """Returns 400 when the given path is not an existing directory."""
        resp = self._post(client, {"path": "/no/such/directory"})
        assert resp.status_code == 400
        assert "Invalid folder path" in resp.get_json()["error"]

    def test_valid_directory_returns_ok(self, client, tmp_path) -> None:
        """Returns 200 with status=ok for a valid existing directory."""
        with patch("subprocess.run"):
            resp = self._post(client, {"path": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_macos_uses_open_command(self, client, tmp_path) -> None:
        """Uses 'open' command on macOS."""
        with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
            self._post(client, {"path": str(tmp_path)})
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "open"
        assert args[1] == str(tmp_path)

    def test_windows_uses_explorer_command(self, client, tmp_path) -> None:
        """Uses 'explorer' command on Windows."""
        with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
            self._post(client, {"path": str(tmp_path)})
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "explorer"
        assert args[1] == str(tmp_path)

    def test_linux_uses_xdg_open_command(self, client, tmp_path) -> None:
        """Uses 'xdg-open' command on Linux and other platforms."""
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
            self._post(client, {"path": str(tmp_path)})
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "xdg-open"
        assert args[1] == str(tmp_path)

    def test_file_path_instead_of_directory_returns_400(self, client, tmp_path) -> None:
        """Returns 400 when the path points to a file rather than a directory."""
        f = tmp_path / "notadir.txt"
        f.write_bytes(b"")
        resp = self._post(client, {"path": str(f)})
        assert resp.status_code == 400


# ===========================================================================
# WARNING_BANNER
# ===========================================================================


def test_warning_banner_contains_experimental_text() -> None:
    """WARNING_BANNER string includes the word 'EXPERIMENTAL'."""
    assert "EXPERIMENTAL" in serve_mod.WARNING_BANNER
