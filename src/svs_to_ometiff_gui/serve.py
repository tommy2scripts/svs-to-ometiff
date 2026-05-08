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
import webbrowser
from queue import Queue
from typing import Optional

from flask import Flask, request, jsonify, Response, render_template

from svs_to_ometiff.converter import convert

app = Flask(__name__)

# In-memory store for progress queues
_progress_queues: dict[str, Queue] = {}
_active_conversion = False
_latest_events: dict[str, dict] = {}

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
    """If path is a bare filename, search common directories for it."""
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
    """Run conversion in a background thread, pushing progress events to the queue."""
    queue = _progress_queues.get(request_id)
    if queue is None:
        return

    def progress_callback(message: str, percent: float = None):
        """Callback passed to the converter to report progress."""
        event = {"message": message}
        if percent is not None:
            event["percent"] = percent
        _latest_events[request_id] = {"type": "progress", "data": event}
        queue.put(("progress", event))

    try:
        convert(
            input_svs=params["input_path"],
            output_ometiff=params.get("output_path"),
            tile_size=params.get("tile_size", 512),
            compression=params.get("compression", "none"),
            num_levels=params.get("num_levels", 3),
            downsample_factor=params.get("downsample_factor", 2),
            progress_logger=progress_callback,
        )
        _latest_events[request_id] = {"type": "complete", "data": {}}
        queue.put(("complete", {}))
    except Exception as exc:
        _latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
        queue.put(("error", {"error": str(exc)}))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def handle_convert():
    global _active_conversion
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
    thread.start()

    return jsonify({"request_id": request_id, "output_path": output_path})


@app.route("/progress/<request_id>")
def stream_progress(request_id: str):
    queue = _progress_queues.get(request_id)
    if queue is None:
        return jsonify({"error": "Invalid request_id"}), 404

    def generate():
        # Replay latest event on SSE reconnect
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
            global _active_conversion
            _active_conversion = False
            _progress_queues.pop(request_id, None)
            _latest_events.pop(request_id, None)

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
    body = request.get_json(force=True)
    folder_path = body.get("path", "").strip()
    if not folder_path or not os.path.isdir(folder_path):
        return jsonify({"error": "Invalid folder path"}), 400

    # macOS
    if sys.platform == "darwin":
        os.system(f'open "{folder_path}"')
    elif sys.platform == "win32":
        os.system(f'explorer "{folder_path}"')
    else:
        os.system(f'xdg-open "{folder_path}"')

    return jsonify({"status": "ok"})


def main():
    print(WARNING_BANNER)
    port = 8765
    url = f"http://127.0.0.1:{port}"
    print(f"  Opening browser at {url}")
    webbrowser.open(url)
    print(f"  Server running on {url}  (Ctrl+C to quit)")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
