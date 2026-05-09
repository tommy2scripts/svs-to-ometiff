"""Conversion service — business logic extracted from Flask routes.

This module owns the background conversion threads, progress queues,
and path resolution logic. Flask routes delegate to this service.
"""

import json
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from pathlib import Path
from queue import Queue
from typing import Optional

from svs_to_ometiff.converter import convert
from svs_to_ometiff.inspect import inspect_svs

from svs_to_ometiff_gui.config import Config
from svs_to_ometiff_gui.db import JobDB
from svs_to_ometiff_gui.models import ConversionJob

# ---------------------------------------------------------------------------
# Progress estimation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Worker Functions (Must be top-level for multiprocessing)
# ---------------------------------------------------------------------------

def _run_single_conversion_worker(request_id: str, kwargs: dict, m_queue):
    """Run conversion in an isolated process."""
    def progress_callback(message: str, **cb_kwargs):
        event: dict = {"message": message}
        percent = cb_kwargs.get("percent")
        if percent is None:
            percent = estimate_percent(message)
        if percent is not None:
            event["percent"] = percent
        if "phase" in cb_kwargs:
            event["phase"] = cb_kwargs["phase"]
        m_queue.put((request_id, "progress", event))

    try:
        convert(**kwargs, progress_logger=progress_callback)
        m_queue.put((request_id, "complete", {}))
    except Exception as exc:  # noqa: BLE001
        m_queue.put((request_id, "error", {"error": str(exc)}))


def _run_batch_conversion_worker(request_id: str, inputs: list[str], output_dir: str, job_template_dict: dict, m_queue):
    """Run batch conversion in an isolated process."""
    total_files = len(inputs)
    compression = job_template_dict.get("compression")
    if compression == "none":
        compression = None

    try:
        for idx, input_path in enumerate(inputs):
            filename = Path(input_path).name
            base = Path(input_path).with_suffix("")
            out_filename = str(base.name) + ".ome.tiff"
            output_path = str(Path(output_dir) / out_filename)

            m_queue.put((request_id, "progress", {
                "message": f"Starting {filename}...",
                "file": filename,
                "file_idx": idx,
                "total_files": total_files,
                "percent": 0,
                "overall_percent": (idx * 100) / total_files,
                "phase": "starting_file",
            }))

            def progress_callback(message: str, current_file=filename, i=idx, **cb_kwargs):
                event: dict = {
                    "message": message,
                    "file": current_file,
                    "file_idx": i,
                    "total_files": total_files,
                }
                percent = cb_kwargs.get("percent")
                if percent is None:
                    percent = estimate_percent(message)
                if percent is not None:
                    event["percent"] = percent
                    event["overall_percent"] = ((i * 100) + percent) / total_files
                else:
                    event["overall_percent"] = (i * 100) / total_files
                if "phase" in cb_kwargs:
                    event["phase"] = cb_kwargs["phase"]
                m_queue.put((request_id, "progress", event))

            convert(
                config_or_input_svs=input_path,
                output_ometiff=output_path,
                tile_size=job_template_dict.get("tile_size", 512),
                compression=compression,
                num_levels=job_template_dict.get("num_levels", 6),
                downsample_factor=job_template_dict.get("downsample_factor", 2),
                edge_mode=job_template_dict.get("edge_mode", "crop"),
                progress_logger=progress_callback,
            )

            m_queue.put((request_id, "progress", {
                "message": f"Completed {filename}",
                "file": filename,
                "file_idx": idx,
                "total_files": total_files,
                "percent": 100,
                "overall_percent": ((idx + 1) * 100) / total_files,
                "phase": "completed_file",
            }))

        m_queue.put((request_id, "complete", {}))
    except Exception as exc:  # noqa: BLE001
        m_queue.put((request_id, "error", {"error": str(exc)}))


# ---------------------------------------------------------------------------
# Service Class
# ---------------------------------------------------------------------------

class ConversionService:
    """Manages conversion jobs, progress queues, and SQLite state."""

    def __init__(self):
        self.config = Config()
        self.db = JobDB()
        self.progress_queues: dict[str, Queue] = {}
        self.latest_events: dict[str, dict] = {}
        self.active_jobs = set()
        
        self._executor = None
        self._m_queue = None
        self._manager = None
        self._dispatcher_thread = None

    def _ensure_executor(self):
        """Lazily initialize the process pool to avoid spawn recursion."""
        if self._executor is None:
            self._manager = Manager()
            self._m_queue = self._manager.Queue()
            self._executor = ProcessPoolExecutor(max_workers=self.config.MAX_CONCURRENT_JOBS)
            self._dispatcher_thread = threading.Thread(target=self._dispatch_events, daemon=True)
            self._dispatcher_thread.start()

    def _dispatch_events(self):
        """Background thread to read from multiprocess queue and write to DB/SSE."""
        while True:
            try:
                request_id, event_type, data = self._m_queue.get()
                
                # Update SQLite
                if event_type == "progress":
                    pct = data.get("percent", 0.0)
                    if "overall_percent" in data:
                        pct = data["overall_percent"]
                    phase = data.get("phase", "")
                    self.db.update_job_progress(request_id, pct, phase)
                elif event_type == "complete":
                    self.db.mark_job_completed(request_id)
                    self.active_jobs.discard(request_id)
                elif event_type == "error":
                    self.db.mark_job_error(request_id, data.get("error", "Unknown error"))
                    self.active_jobs.discard(request_id)

                # Update memory for SSE
                self.latest_events[request_id] = {"type": event_type, "data": data}
                if request_id in self.progress_queues:
                    self.progress_queues[request_id].put((event_type, data))
            except Exception:
                logging.getLogger(__name__).exception("Failed to dispatch/update job progress")

    @property
    def is_active(self) -> bool:
        return len(self.active_jobs) > 0

    def create_job(self, job_type: str, input_path: str, output_path: str) -> str:
        """Allocate a new request_id, DB row, and progress queue."""
        request_id = str(uuid.uuid4())
        self.progress_queues[request_id] = Queue()
        self.active_jobs.add(request_id)
        self.db.create_job(request_id, job_type, input_path, output_path)
        return request_id

    def cleanup_job(self, request_id: str) -> None:
        """Remove a finished job's in-memory queue (DB history remains)."""
        self.progress_queues.pop(request_id, None)
        self.latest_events.pop(request_id, None)

    # ------------------------------------------------------------------
    # Single conversion
    # ------------------------------------------------------------------
    def start_conversion(self, job: ConversionJob) -> str:
        """Create job, spawn process, return request_id."""
        self._ensure_executor()
        request_id = self.create_job("single", job.input_path, job.output_path)
        job.request_id = request_id
        
        # Submit to process pool
        self._executor.submit(
            _run_single_conversion_worker,
            request_id,
            job.to_converter_kwargs(),
            self._m_queue,
        )
        return request_id

    # ------------------------------------------------------------------
    # Batch conversion
    # ------------------------------------------------------------------
    def start_batch_conversion(
        self,
        inputs: list[str],
        output_dir: str,
        job_template: ConversionJob,
    ) -> str:
        """Create job, spawn batch process, return request_id."""
        self._ensure_executor()
        request_id = self.create_job("batch", f"{len(inputs)} files", output_dir)
        
        # Submit to process pool
        # Note: We pass a simple dict to the worker because it must be pickleable
        template_dict = {
            "compression": job_template.compression,
            "tile_size": job_template.tile_size,
            "num_levels": job_template.num_levels,
            "downsample_factor": job_template.downsample_factor,
            "edge_mode": job_template.edge_mode,
        }
        self._executor.submit(
            _run_batch_conversion_worker,
            request_id,
            inputs,
            output_dir,
            template_dict,
            self._m_queue,
        )
        return request_id

    # ------------------------------------------------------------------
    # Slide inspection
    # ------------------------------------------------------------------
    @staticmethod
    def inspect_slide(path: str) -> dict:
        return inspect_svs(path)
