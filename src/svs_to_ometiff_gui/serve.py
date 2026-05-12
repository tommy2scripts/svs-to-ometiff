#!/usr/bin/env python3
"""
svs-to-ometiff GUI — Flask web server.

Usage:
    python -m svs_to_ometiff_gui.serve

Opens browser at http://127.0.0.1:8765
"""

import os
import sys
import json
import uuid
import threading
import subprocess
import webbrowser
from queue import Queue
from typing import Optional

from flask import Flask, request, jsonify, Response, render_template

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff.converter import convert

app = Flask(__name__)

# In-memory store for progress queues
_progress_queues: dict[str, Queue] = {}
_active_conversion = False
_latest_events: dict[str, dict] = {}
_conversion_lock = threading.Lock()
_conversion_thread: Optional[threading.Thread] = None

WARNING_BANNER = """
\033[33m
  ╔══════════════════════════════════════════════════════════════╗
  ║                                                            ║
  ║   \033[1mEXPERIMENTAL WARNING\033[22m                                          ║
  ║                                                            ║
  ║   This GUI is experimental and not yet thoroughly tested.  ║
  ║   Use with caution on production data.                     ║
  ║   Always verify outputs.                                   ║
  ║                                                            ║
  ╚══════════════════════════════════════════════════════════════╝
\033[0m
"""


def _resolve_path(path: str) -> Optional[str]:
    """
    Locate an existing file matching `path`, searching common user locations when `path` is a bare filename.
    
    Parameters:
        path (str): A file path or bare filename to resolve.
    
    Returns:
        Optional[str]: The original `path` if it exists, or a matching candidate from ~/Downloads, ~/Desktop, or the current working directory when `path` is a basename; `None` if no existing file is found.
    """
    if os.path.isfile(path):
        return path
    # Check if it's just a basename (no directory separator)
    if "/" not in path and "\\" not in path:
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Downloads", path),
            os.path.join(home, "Desktop", path),
            os.path.join(os.getcwd(), path),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _run_conversion(request_id: str, params: dict):
    """
    Run a conversion task for the given request and publish progress, completion, or error events to the per-request queue.
    
    This function looks up the queue registered for request_id in _progress_queues; if none exists it returns immediately. While the conversion runs it updates _latest_events[request_id] and pushes tuples into the queue in the form (event_type, data):
    
    - "progress": data is {"message": str, "percent": float} where "percent" is present only when provided by the converter.
    - "complete": data is an empty dict.
    - "error": data is {"error": str} containing the exception string.
    
    Parameters:
        request_id (str): Identifier for the conversion request whose queue and latest-event entry will be updated.
        params (dict): Conversion parameters. Expected keys:
            - "input_path" (str): path to the input .svs file (required).
            - "output_path" (str): path for the output .ome.tiff (optional).
            - "tile_size" (int): tile size to pass to the converter (optional, default 512).
            - "compression" (str): compression setting for the converter (optional).
            - "num_levels" (int): number of pyramid levels (optional).
            - "downsample_factor" (int): downsample factor between levels (optional).
    """
    queue = _progress_queues.get(request_id)
    if queue is None:
        return

    def progress_callback(message: str, percent: float = None):
        """
        Publish a progress event for the current conversion request.
        
        Builds an event containing a human-readable message and an optional completion percentage, stores it as the latest event for the request, and enqueues it for streaming to connected clients.
        
        Parameters:
            message (str): Human-readable progress message describing the current step.
            percent (float | None): Optional completion percentage (e.g., 0.0–100.0); omitted when unknown.
        """
        event = {"message": message}
        if percent is not None:
            event["percent"] = percent
        _latest_events[request_id] = {"type": "progress", "data": event}
        queue.put(("progress", event))

    try:
        # Normalize: the CLI/Config API uses None for uncompressed,
        # but the GUI sends the string "none"
        compression = params.get("compression", "none")
        compression = None if compression == "none" else compression

        config = ConvertConfig(
            input_svs=params["input_path"],
            output_ometiff=params.get("output_path"),
            tile_size=int(params.get("tile_size", 512)),
            compression=compression,
            num_levels=int(params.get("num_levels", 3)),
            downsample_factor=int(params.get("downsample_factor", 2)),
            verbose=True,
            progress_logger=progress_callback,
        )

        convert(config)
        _latest_events[request_id] = {"type": "complete", "data": {}}
        queue.put(("complete", {}))
    except Exception as exc:
        _latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
        queue.put(("error", {"error": str(exc)}))


@app.route("/")
def index():
    """
    Render and return the application's index HTML page.
    
    Returns:
        A Flask response object containing the rendered `index.html` template.
    """
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def handle_convert():
    """
    Handle a request to start a new SVS-to-OME-TIFF conversion and queue its background execution.
    
    Validates the incoming JSON payload, resolves and checks the input SVS path, derives or validates the output path and its directory writability, validates optional numeric parameters (e.g., `tile_size`), ensures only one conversion runs at a time, registers per-request progress state, and starts a daemon thread to perform the conversion.
    
    Returns:
        A Flask JSON response:
        - On success: JSON `{"request_id": <uuid>, "output_path": <path>}` with HTTP 200.
        - If a conversion is already running: JSON `{"error": <message>}` with HTTP 409.
        - On validation failure (missing/invalid input_path, non-.svs input, unwritable output directory, invalid tile_size, or unresolved path): JSON `{"error": <message>}` with HTTP 400.
    """
    global _active_conversion, _conversion_thread
    with _conversion_lock:
        if _active_conversion:
            return jsonify({"error": "A conversion is already running. Please wait for it to complete."}), 409

    body = request.get_json(force=True)
    input_path = body.get("input_path", "").strip()

    if not input_path:
        return jsonify({"error": "input_path is required"}), 400

    # Resolve the path: if it's a bare filename, search common directories
    resolved = _resolve_path(input_path)
    if resolved is None:
        return jsonify({
            "error": (
                f"File not found: {input_path}\n\n"
                "If you only provided a filename, try the full path.\n\n"
                "On macOS: Right-click the file in Finder, hold the Option key, "
                'then choose Copy "..." as Pathname — paste that full path above.'
            )
        }), 400

    input_path = resolved

    if not input_path.lower().endswith(".svs"):
        return jsonify({"error": "Input file must have .svs extension"}), 400

    # Auto-derive output path if not provided
    output_path = body.get("output_path", "").strip()
    if not output_path:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".ome.tiff"

    # Validate output directory is writable
    output_dir = os.path.dirname(output_path) or "."
    if not os.access(output_dir, os.W_OK):
        return jsonify({"error": f"Output directory is not writable: {output_dir}"}), 400

    # Validate tile_size
    tile_size = body.get("tile_size")
    if tile_size is not None:
        try:
            tile_size_val = int(tile_size)
            if tile_size_val <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({"error": "tile_size must be a positive integer"}), 400

    request_id = str(uuid.uuid4())
    queue: Queue = Queue()

    with _conversion_lock:
        _progress_queues[request_id] = queue
        _active_conversion = True

        params = {
            "input_path": input_path,
            "output_path": output_path,
        }
        for key in ("tile_size", "compression", "num_levels", "downsample_factor"):
            val = body.get(key)
            if val is not None:
                params[key] = val

        thread = threading.Thread(
            target=_run_conversion,
            args=(request_id, params),
            daemon=True,
        )
        _conversion_thread = thread
        thread.start()

    return jsonify({"request_id": request_id, "output_path": output_path})


@app.route("/progress/<request_id>")
def stream_progress(request_id: str):
    """
    Stream server-sent events for conversion progress identified by `request_id`.
    
    Replays the last cached event for the request (if any) immediately on connect, then streams queued progress events until a `complete` or `error` event is emitted. When the stream ends the function cleans up per-request state and resets the active-conversion flag.
    
    Parameters:
        request_id (str): Identifier of the conversion request whose progress should be streamed.
    
    Returns:
        Response: A Flask `Response` that streams SSE events (`event: progress`, `event: complete`, `event: error`) with JSON payloads for each event.
    """
    queue = _progress_queues.get(request_id)
    if queue is None:
        return jsonify({"error": "Invalid request_id"}), 404

    def generate():
        # Replay latest event on SSE reconnect
        """
        Stream server-sent events (SSE) for a conversion request and perform cleanup when the stream ends.
        
        Replays the last cached event for the request (complete, error, or a progress update) immediately when a client reconnects, then yields queued events from the per-request queue until a `complete` or `error` event is emitted. When the generator exits it joins the conversion thread (with a short timeout), removes per-request state from internal registries, and clears the active-conversion flag.
        
        Returns:
            An iterator that yields SSE-formatted strings (each string contains an `event: <type>` line and a `data: <json>` line, terminated by a blank line).
        """
        latest = _latest_events.get(request_id)
        if latest:
            event_type = latest["type"]
            data = latest["data"]
            if event_type == "complete":
                yield f"event: complete\ndata: {json.dumps(data)}\n\n"
                return
            elif event_type == "error":
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
                return
            else:
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"

        try:
            while True:
                event_type, data = queue.get()
                if event_type == "progress":
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                elif event_type == "complete":
                    yield f"event: complete\ndata: {json.dumps(data)}\n\n"
                    break
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps(data)}\n\n"
                    break
        finally:
            global _active_conversion, _conversion_thread
            with _conversion_lock:
                if _conversion_thread is not None:
                    _conversion_thread.join(timeout=1.0)
                    _conversion_thread = None
                _progress_queues.pop(request_id, None)
                _latest_events.pop(request_id, None)
                _active_conversion = False

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/open_folder", methods=["POST"])
def handle_open_folder():
    """
    Open a filesystem folder specified in the request JSON and return the operation status.
    
    Expects a JSON body with a "path" field containing the folder path string. If the path is not a non-empty string or does not refer to an existing directory, the endpoint returns an error response with HTTP 400.
    
    On success, opens the folder using the platform's default file manager:
    - macOS: `open`
    - Windows: `explorer`
    - Other: `xdg-open`
    
    Returns:
        A Flask JSON response: `{"status": "ok"}` on success, or `{"error": "Invalid folder path"}` with HTTP 400 when the input path is missing or not a directory.
    """
    body = request.get_json(force=True)
    folder_path = body.get("path", "").strip()
    if not folder_path or not os.path.isdir(folder_path):
        return jsonify({"error": "Invalid folder path"}), 400

    # macOS
    if sys.platform == "darwin":
        subprocess.run(["open", folder_path])
    elif sys.platform == "win32":
        subprocess.run(["explorer", folder_path])
    else:
        subprocess.run(["xdg-open", folder_path])

    return jsonify({"status": "ok"})


def main():
    """
    Start the GUI server, open the default web browser to the server URL, and block while serving requests.
    
    Prints the experimental warning banner, opens the default browser at http://127.0.0.1:8765, and runs the Flask app bound to 127.0.0.1:8765 until the process is terminated (e.g., Ctrl+C).
    """
    print(WARNING_BANNER)
    port = 8765
    url = f"http://127.0.0.1:{port}"
    print(f"  Opening browser at {url}")
    webbrowser.open(url)
    print(f"  Server running on {url}  (Ctrl+C to quit)")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
