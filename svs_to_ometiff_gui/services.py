"""Conversion service — business logic extracted from Flask routes.

This module owns the background conversion threads, progress queues,
and path resolution logic. Flask routes delegate to this service.
"""

import json
import os
import re
import threading
import uuid
from pathlib import Path
from queue import Queue
from typing import Optional

from svs_to_ometiff.converter import convert
from svs_to_ometiff.inspect import inspect_svs

from svs_to_ometiff_gui.models import ConversionJob

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


def estimate_percent(message: str) -> Optional[float]:
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
    if message.lower().startswith("  level"):
        return 92.0
    if "done in" in low:
        return 100.0

    return None


def resolve_path(path: str) -> Optional[str]:
    """If path is a bare filename, search common directories for it."""
    if not path:
        return None
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


class ConversionService:
    """Manages conversion jobs, progress queues, and state."""

    def __init__(self):
        self.progress_queues: dict[str, Queue] = {}
        self.latest_events: dict[str, dict] = {}
        self.active: bool = False

    @property
    def is_active(self) -> bool:
        return self.active

    def create_job(self) -> str:
        """Allocate a new request_id and progress queue."""
        request_id = str(uuid.uuid4())
        self.progress_queues[request_id] = Queue()
        self.active = True
        return request_id

    def cleanup_job(self, request_id: str) -> None:
        """Remove a finished job's queue and reset state."""
        self.active = False
        self.progress_queues.pop(request_id, None)
        self.latest_events.pop(request_id, None)

    # ------------------------------------------------------------------
    # Single conversion
    # ------------------------------------------------------------------
    def run_conversion(self, request_id: str, job: ConversionJob) -> None:
        """Run conversion in a background thread, pushing progress events."""
        queue = self.progress_queues.get(request_id)
        if queue is None:
            return

        def progress_callback(message: str):
            percent = estimate_percent(message)
            event: dict = {"message": message}
            if percent is not None:
                event["percent"] = percent
            self.latest_events[request_id] = {"type": "progress", "data": event}
            queue.put(("progress", event))

        try:
            kwargs = job.to_converter_kwargs()
            convert(**kwargs, progress_logger=progress_callback)
            self.latest_events[request_id] = {"type": "complete", "data": {}}
            queue.put(("complete", {}))
        except Exception as exc:  # noqa: BLE001
            self.latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
            queue.put(("error", {"error": str(exc)}))

    def start_conversion(self, job: ConversionJob) -> str:
        """Create job, spawn background thread, return request_id."""
        request_id = self.create_job()
        job.request_id = request_id
        thread = threading.Thread(
            target=self.run_conversion,
            args=(request_id, job),
            daemon=True,
        )
        thread.start()
        return request_id

    # ------------------------------------------------------------------
    # Batch conversion
    # ------------------------------------------------------------------
    def run_batch_conversion(
        self,
        request_id: str,
        inputs: list[str],
        output_dir: str,
        job_template: ConversionJob,
    ) -> None:
        """Run batch conversion, pushing per-file progress events."""
        queue = self.progress_queues.get(request_id)
        if queue is None:
            return

        total_files = len(inputs)
        compression = job_template.compression
        if compression == "none":
            compression = None

        try:
            for idx, input_path in enumerate(inputs):
                filename = Path(input_path).name
                base = Path(input_path).with_suffix("")
                out_filename = str(base.name) + ".ome.tiff"
                output_path = str(Path(output_dir) / out_filename)

                queue.put(("progress", {
                    "message": f"Starting {filename}...",
                    "file": filename,
                    "file_idx": idx,
                    "total_files": total_files,
                    "percent": 0,
                }))

                def progress_callback(message: str, current_file=filename, i=idx):
                    percent = estimate_percent(message)
                    event: dict = {
                        "message": message,
                        "file": current_file,
                        "file_idx": i,
                        "total_files": total_files,
                    }
                    if percent is not None:
                        event["percent"] = percent
                        event["overall_percent"] = ((i * 100) + percent) / total_files
                    self.latest_events[request_id] = {"type": "progress", "data": event}
                    queue.put(("progress", event))

                convert(
                    input_svs=input_path,
                    output_ometiff=output_path,
                    tile_size=job_template.tile_size,
                    compression=compression,
                    num_levels=job_template.num_levels,
                    downsample_factor=job_template.downsample_factor,
                    edge_mode=job_template.edge_mode,
                    progress_logger=progress_callback,
                )

                queue.put(("progress", {
                    "message": f"Completed {filename}",
                    "file": filename,
                    "file_idx": idx,
                    "total_files": total_files,
                    "percent": 100,
                    "overall_percent": ((idx + 1) * 100) / total_files,
                }))

            self.latest_events[request_id] = {"type": "complete", "data": {}}
            queue.put(("complete", {}))
        except Exception as exc:  # noqa: BLE001
            self.latest_events[request_id] = {"type": "error", "data": {"error": str(exc)}}
            queue.put(("error", {"error": str(exc)}))

    def start_batch_conversion(
        self,
        inputs: list[str],
        output_dir: str,
        job_template: ConversionJob,
    ) -> str:
        """Create job, spawn batch thread, return request_id."""
        request_id = self.create_job()
        thread = threading.Thread(
            target=self.run_batch_conversion,
            args=(request_id, inputs, output_dir, job_template),
            daemon=True,
        )
        thread.start()
        return request_id

    # ------------------------------------------------------------------
    # Slide inspection (thin wrapper)
    # ------------------------------------------------------------------
    @staticmethod
    def inspect_slide(path: str) -> dict:
        """Inspect an SVS file and return metadata dict."""
        return inspect_svs(path)
