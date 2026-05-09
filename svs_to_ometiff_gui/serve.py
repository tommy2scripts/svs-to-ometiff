#!/usr/bin/env python3
"""
svs-to-ometiff GUI — Flask web server.

Usage:
    python -m svs_to_ometiff_gui.serve

Opens browser at http://127.0.0.1:8765
"""

import json
import os
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
from pathlib import Path
from queue import Queue
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from svs_to_ometiff.converter import convert
from svs_to_ometiff.inspect import inspect_svs

app = Flask(__name__)

# In-memory store for progress queues
_progress_queues: dict[str, Queue] = {}
_state = {"active": False}
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

# ---------------------------------------------------------------------------
# Progress estimation
# ---------------------------------------------------------------------------
# The converter emits text messages via progress_logger. We parse these to
# estimate a percentage using a phased model:
#   0 - 10 %   reading metadata / setup
#  10 - 60 %   tile decoding  (track "Tile row X of Y")
#  60 – 85 %   pyramid building
#  85 – 98 %   writing OME-TIFF
#  100 %       done

_TILE_ROW_RE = re.compile(r"Tile row\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


def _estimate_percent(message: str) -> Optional[float]:
    """Parse a converter progress message and return an estimated percent."""
    msg = message.strip()

    # Tile row progress → 10-60%
    m = _TILE_ROW_RE.search(msg)
    if m:
        current, total = int(m.group(1)), int(m.group(2))
        if total > 0:
            frac = current / total
            return round(10 + frac * 50, 1)

    low = msg.lower()
    if "reading" in low or "metadata" in low or "opening" in low:
        return 5.0
    if "building" in low and "pyramid" in low:
        return 62.0
    if "level" in low and "memmap" in low:
        return 70.0
    if "pyramid built" in low:
        return 82.0
    if "writing" in low and "ome" in low.replace("-", ""):
        return 86.0
    if low.startswith("  level"):
        return 92.0
    if "done in" in low:
        return 100.0

    return None


def _resolve_path(path: str) -> Optional[str]:
    """If path is a bare filename, search common directories for it."""
    p = Path(path)
    if p.is_file():
        return str(p)
    # Check if it's just a basename (no directory separator)
    if "/" not in path and "\\" not in path:
        home = Path.home()
        candidates = [
            home / "Downloads" / path,
            home / "Desktop" / path,
            Path.cwd() / path,
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
    return None


def _run_conversion(request_id: str, params: dict):
    """Run conversion in a background thread, pushing progress events to the queue."""
    queue = _progress_queues.get(request_id)
    if queue is None:
        return

    def progress_callback(message: str):
        """Callback passed to the converter to report progress."""
        percent = _estimate_percent(message)
        event: dict = {"message": message}
        if percent is not None:
            event["percent"] = percent
        _latest_events[request_id] = {"type": "progress", "data": event}
        queue.put(("progress", event))

    try:
        compression = params.get("compression", "lzw")
        if compression == "none":
            compression = None

        convert(
            input_svs=params["input_path"],
            output_ometiff=params.get("output_path"),
            tile_size=params.get("tile_size", 512),
            compression=compression,
            num_levels=params.get("num_levels", 6),
            downsample_factor=params.get("downsample_factor", 2),
            edge_mode=params.get("edge_mode", "crop"),
            progress_logger=progress_callback,
        )
        _latest_events[request_id] = {"type": "complete", "data": {}}
        queue.put(("complete", {}))
    except Exception as exc:  # noqa: BLE001
        _latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
        queue.put(("error", {"error": str(exc)}))


def _run_batch_conversion(request_id: str, inputs: list[str], output_dir: str, params: dict):
    queue = _progress_queues.get(request_id)
    if queue is None:
        return

    total_files = len(inputs)
    compression = params.get("compression", "lzw")
    if compression == "none":
        compression = None

    try:
        for idx, input_path in enumerate(inputs):
            filename = Path(input_path).name
            base = Path(input_path).with_suffix("")
            out_filename = str(base.name) + ".ome.tiff"
            output_path = str(Path(output_dir) / out_filename)

            # Signal file start
            queue.put(("progress", {"message": f"Starting {filename}...", "file": filename, "file_idx": idx, "total_files": total_files, "percent": 0}))
            
            def progress_callback(message: str, current_file=filename, i=idx):
                percent = _estimate_percent(message)
                event: dict = {"message": message, "file": current_file, "file_idx": i, "total_files": total_files}
                if percent is not None:
                    event["percent"] = percent
                    event["overall_percent"] = ((i * 100) + percent) / total_files
                _latest_events[request_id] = {"type": "progress", "data": event}
                queue.put(("progress", event))

            convert(
                input_svs=input_path,
                output_ometiff=output_path,
                tile_size=params.get("tile_size", 512),
                compression=compression,
                num_levels=params.get("num_levels", 6),
                downsample_factor=params.get("downsample_factor", 2),
                edge_mode=params.get("edge_mode", "crop"),
                progress_logger=progress_callback,
            )
            
            queue.put(("progress", {"message": f"Completed {filename}", "file": filename, "file_idx": idx, "total_files": total_files, "percent": 100, "overall_percent": ((idx+1)*100)/total_files}))

        _latest_events[request_id] = {"type": "complete", "data": {}}
        queue.put(("complete", {}))
    except Exception as exc:  # noqa: BLE001
        _latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
        queue.put(("error", {"error": str(exc)}))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/inspect")
def handle_inspect():
    """Return slide metadata without decoding any tiles."""
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path query parameter is required"}), 400

    resolved = _resolve_path(path)
    if resolved is None:
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        info = inspect_svs(resolved)
        # Add the resolved path so the frontend knows the real path
        info["resolved_path"] = resolved
        # Ensure JSON-serializable types
        return jsonify(info)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400


@app.route("/convert", methods=["POST"])
def handle_convert():
    if _state["active"]:
        return jsonify({"error": "A conversion is already running."}), 409

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
        base = Path(input_path).with_suffix("")
        output_path = str(base) + ".ome.tiff"

    # Validate output directory is writable
    out_path_obj = Path(output_path)
    output_dir = out_path_obj.parent if out_path_obj.parent.name else Path.cwd()
    if not os.access(output_dir, os.W_OK):
        return jsonify({"error": f"Output directory is not writable: {output_dir}"}), 400

    # Validate tile_size
    tile_size = body.get("tile_size")
    if tile_size is not None:
        try:
            tile_size_val = int(tile_size)
            if tile_size_val <= 0:
                raise ValueError("Must be positive")
        except (ValueError, TypeError):
            return jsonify({"error": "tile_size must be a positive integer"}), 400

    # Validate integer params
    for param_name in ("num_levels", "downsample_factor"):
        val = body.get(param_name)
        if val is not None:
            try:
                val_int = int(val)
                if val_int <= 0:
                    raise ValueError("Must be positive")
            except (ValueError, TypeError):
                return jsonify({"error": f"{param_name} must be a positive integer"}), 400

    request_id = str(uuid.uuid4())
    queue: Queue = Queue()
    _progress_queues[request_id] = queue
    _state["active"] = True

    params = {
        "input_path": input_path,
        "output_path": output_path,
    }
    config_keys = ("tile_size", "compression", "num_levels", "downsample_factor", "edge_mode")
    for key in config_keys:
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


@app.route("/convert/batch", methods=["POST"])
def handle_convert_batch():
    if _state["active"]:
        return jsonify({"error": "A conversion is already running."}), 409

    body = request.get_json(force=True)
    inputs = body.get("inputs", [])
    output_dir = body.get("output_dir", "").strip()

    if not inputs or not isinstance(inputs, list):
        return jsonify({"error": "inputs must be a non-empty list of paths"}), 400
    
    if not output_dir:
        # Default to the directory of the first valid input
        if len(inputs) > 0:
            first_resolved = _resolve_path(inputs[0])
            if first_resolved:
                output_dir = str(Path(first_resolved).parent)
            else:
                output_dir = str(Path.cwd())
        else:
            output_dir = str(Path.cwd())

    # Resolve all inputs
    resolved_inputs = []
    for p in inputs:
        resolved = _resolve_path(p)
        if resolved is None:
            return jsonify({"error": f"File not found: {p}"}), 400
        if not resolved.lower().endswith(".svs"):
            return jsonify({"error": f"File must be .svs: {p}"}), 400
        resolved_inputs.append(resolved)

    # Validate output dir
    out_dir_obj = Path(output_dir)
    if not out_dir_obj.is_dir() and not out_dir_obj.parent.is_dir():
         return jsonify({"error": f"Invalid output directory: {output_dir}"}), 400
    
    out_dir_obj.mkdir(parents=True, exist_ok=True)
    if not os.access(output_dir, os.W_OK):
        return jsonify({"error": f"Output directory is not writable: {output_dir}"}), 400

    # Validate integer params
    for int_val in ("tile_size", "num_levels", "downsample_factor"):
        val = body.get(int_val)
        if val is not None:
            try:
                v = int(val)
                if v <= 0:
                    raise ValueError("Must be positive")
            except Exception:  # noqa: BLE001
                return jsonify({"error": f"{int_val} must be positive int"}), 400

    request_id = str(uuid.uuid4())
    queue: Queue = Queue()
    _progress_queues[request_id] = queue
    _state["active"] = True

    params = {}
    config_keys = ("tile_size", "compression", "num_levels", "downsample_factor", "edge_mode")
    for key in config_keys:
        val = body.get(key)
        if val is not None:
            params[key] = val

    thread = threading.Thread(
        target=_run_batch_conversion,
        args=(request_id, resolved_inputs, output_dir, params),
        daemon=True,
    )
    thread.start()

    return jsonify({"request_id": request_id, "output_dir": output_dir, "count": len(resolved_inputs)})


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
            _state["active"] = False
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


@app.route("/browse_file")
def handle_browse_file():
    """Trigger a native file dialog on the server host to bypass browser path security."""
    import subprocess
    import sys
    path = ""
    try:
        if sys.platform == "darwin":
            cmd = ['osascript', '-e', 'POSIX path of (choose file of type {"public.data"})']
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                path = res.stdout.strip()
        else:
            code = "import tkinter as tk, tkinter.filedialog as fd; root=tk.Tk(); root.withdraw(); root.call('wm','attributes','.','-topmost',True); print(fd.askopenfilename())"
            res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
            if res.returncode == 0:
                path = res.stdout.strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"path": path})


@app.route("/browse_files")
def handle_browse_files():
    """Trigger a native file dialog for multiple files on the server host."""
    import subprocess
    import sys
    paths = []
    try:
        if sys.platform == "darwin":
            # AppleScript to choose multiple files and return their POSIX paths separated by newline
            script = 'set theFiles to choose file of type {"public.data"} with multiple selections allowed\nset thePaths to ""\nrepeat with aFile in theFiles\nset thePaths to thePaths & POSIX path of aFile & "\\n"\nend repeat\nreturn thePaths'
            cmd = ['osascript', '-e', script]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                paths = [p for p in res.stdout.strip().split('\n') if p]
        else:
            code = "import tkinter as tk, tkinter.filedialog as fd; root=tk.Tk(); root.withdraw(); root.call('wm','attributes','.','-topmost',True); print('\\n'.join(fd.askopenfilenames()))"
            res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
            if res.returncode == 0:
                paths = [p for p in res.stdout.strip().split('\n') if p]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"paths": paths})


@app.route("/open_folder", methods=["POST"])
def handle_open_folder():
    body = request.get_json(force=True)
    folder_path = body.get("path", "").strip()
    if not folder_path or not Path(folder_path).is_dir():
        return jsonify({"error": "Invalid folder path"}), 400

    # Securely open folder without shell execution
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", folder_path], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", folder_path], check=False)
        else:
            subprocess.run(["xdg-open", folder_path], check=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Failed to open folder: {exc}"}), 500

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
