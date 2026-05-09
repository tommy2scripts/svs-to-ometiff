#!/usr/bin/env python3
"""
svs-to-ometiff GUI — Flask web server.

Usage:
    python -m svs_to_ometiff_gui.serve

Opens browser at http://127.0.0.1:8765
"""

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from svs_to_ometiff_gui.file_dialogs import get_dialog_strategy
from svs_to_ometiff_gui.models import ConversionJob
from svs_to_ometiff_gui.services import ConversionService, resolve_path

app = Flask(__name__)

# Singleton service instance
_service = ConversionService()
_dialog = get_dialog_strategy()

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
# Backward-compatible aliases (used by existing tests)
# ---------------------------------------------------------------------------
def _resolve_path(path: str):
    """Thin wrapper kept for backward compatibility with tests."""
    return resolve_path(path)


def _estimate_percent(message: str):
    """Thin wrapper kept for backward compatibility with tests."""
    from svs_to_ometiff_gui.services import estimate_percent
    return estimate_percent(message)


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

    resolved = resolve_path(path)
    if resolved is None:
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        info = _service.inspect_slide(resolved)
        # Add the resolved path so the frontend knows the real path
        info["resolved_path"] = resolved
        return jsonify(info)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400


@app.route("/convert", methods=["POST"])
def handle_convert():
    if _service.is_active:
        return jsonify({"error": "A conversion is already running."}), 409

    body = request.get_json(force=True)
    input_path = body.get("input_path", "").strip()

    if not input_path:
        return jsonify({"error": "input_path is required"}), 400

    # Resolve the path: if it's a bare filename, search common directories
    resolved = resolve_path(input_path)
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

    # Build a typed ConversionJob
    compression = body.get("compression", "lzw")
    job = ConversionJob(
        input_path=input_path,
        output_path=output_path,
        tile_size=int(body.get("tile_size", 512)),
        compression=compression,
        num_levels=int(body.get("num_levels", 6)),
        downsample_factor=int(body.get("downsample_factor", 2)),
        edge_mode=body.get("edge_mode", "crop"),
    )

    request_id = _service.start_conversion(job)

    return jsonify({"request_id": request_id, "output_path": output_path})


@app.route("/convert/batch", methods=["POST"])
def handle_convert_batch():
    if _service.is_active:
        return jsonify({"error": "A conversion is already running."}), 409

    body = request.get_json(force=True)
    inputs = body.get("inputs", [])
    output_dir = body.get("output_dir", "").strip()

    if not inputs or not isinstance(inputs, list):
        return jsonify({"error": "inputs must be a non-empty list of paths"}), 400

    if not output_dir:
        # Default to the directory of the first valid input
        if len(inputs) > 0:
            first_resolved = resolve_path(inputs[0])
            if first_resolved:
                output_dir = str(Path(first_resolved).parent)
            else:
                output_dir = str(Path.cwd())
        else:
            output_dir = str(Path.cwd())

    # Resolve all inputs
    resolved_inputs = []
    for p in inputs:
        resolved = resolve_path(p)
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

    # Build job template
    compression = body.get("compression", "lzw")
    job_template = ConversionJob(
        input_path="",  # filled per-file
        tile_size=int(body.get("tile_size", 512)),
        compression=compression,
        num_levels=int(body.get("num_levels", 6)),
        downsample_factor=int(body.get("downsample_factor", 2)),
        edge_mode=body.get("edge_mode", "crop"),
    )

    request_id = _service.start_batch_conversion(
        resolved_inputs, output_dir, job_template
    )

    return jsonify({"request_id": request_id, "output_dir": output_dir, "count": len(resolved_inputs)})


@app.route("/progress/<request_id>")
def stream_progress(request_id: str):
    queue = _service.progress_queues.get(request_id)
    if queue is None:
        return jsonify({"error": "Invalid request_id"}), 404

    def generate():
        # Replay latest event on SSE reconnect
        latest = _service.latest_events.get(request_id)
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
            _service.cleanup_job(request_id)

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
    """Trigger a native file dialog on the server host."""
    try:
        path = _dialog.pick_file()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"path": path})


@app.route("/browse_files")
def handle_browse_files():
    """Trigger a native multi-file dialog on the server host."""
    try:
        paths = _dialog.pick_files()
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
