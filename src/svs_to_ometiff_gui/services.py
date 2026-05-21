"""Conversion service — business logic extracted from Flask routes.

This module owns the background conversion threads, progress queues,
and path resolution logic. Flask routes delegate to this service.
"""

import logging
import re
import signal
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from pathlib import Path
from queue import Empty, Queue
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


def batch_output_path(input_path: str, output_dir: str) -> str:
    """Return the GUI batch destination path for one input slide."""
    base = Path(input_path).with_suffix("")
    return str(Path(output_dir) / f"{base.name}.ome.tiff")


def find_duplicate_batch_outputs(
    inputs: list[str],
    output_dir: str,
) -> dict[str, list[str]]:
    """Return destination paths that would be written by multiple inputs."""
    outputs: dict[str, tuple[str, list[str]]] = {}
    for input_path in inputs:
        out_path = batch_output_path(input_path, output_dir)
        key = str(Path(out_path).resolve()).casefold()
        if key not in outputs:
            outputs[key] = (out_path, [])
        outputs[key][1].append(input_path)

    return {
        out_path: input_paths
        for out_path, input_paths in outputs.values()
        if len(input_paths) > 1
    }


def format_duplicate_batch_outputs(duplicates: dict[str, list[str]]) -> str:
    """Build a compact user-facing error for colliding batch outputs."""
    lines = ["Batch output path collision detected."]
    for out_path, input_paths in duplicates.items():
        lines.append(f"{out_path}:")
        for input_path in input_paths:
            lines.append(f"  - {input_path}")
    lines.append("Use distinct filenames or split the batch to avoid overwriting outputs.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Worker Functions (Must be top-level for multiprocessing)
# ---------------------------------------------------------------------------

def _install_worker_signal_handlers() -> None:
    """Install signal handlers in worker processes for graceful cancellation.

    Sets a module-level threading.Event in ``svs_to_ometiff.converter`` so
    the conversion pipeline can check for cancellation between stages.
    """
    from svs_to_ometiff.converter import _shutdown_event as _converter_shutdown_event

    def _handle_worker_shutdown(signum, frame):
        _converter_shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_worker_shutdown)
        except (ValueError, OSError):
            pass


def _run_single_conversion_worker(request_id: str, kwargs: dict, m_queue):
    """Run conversion in an isolated process."""
    _install_worker_signal_handlers()

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
        result = convert(**kwargs, progress_logger=progress_callback)
        complete_data = {}
        cleanup_warning = result.get("cleanup_warning")
        if cleanup_warning:
            complete_data["cleanup_warning"] = cleanup_warning
        m_queue.put((request_id, "complete", complete_data))
    except Exception as exc:  # noqa: BLE001
        logging.exception("Single conversion worker failed")
        m_queue.put((request_id, "error", {"error": str(exc)}))


def _run_batch_conversion_worker(request_id: str, inputs: list[str], output_dir: str, job_template_dict: dict, m_queue):
    """Run batch conversion in an isolated process."""
    _install_worker_signal_handlers()
    total_files = len(inputs)
    compression = job_template_dict.get("compression")
    if compression == "none":
        compression = None

    try:
        duplicates = find_duplicate_batch_outputs(inputs, output_dir)
        if duplicates:
            raise ValueError(format_duplicate_batch_outputs(duplicates))

        for idx, input_path in enumerate(inputs):
            filename = Path(input_path).name
            output_path = batch_output_path(input_path, output_dir)

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

            result = convert(
                config_or_input_svs=input_path,
                output_ometiff=output_path,
                tile_size=job_template_dict.get("tile_size", 1024),
                compression=compression,
                num_levels=job_template_dict.get("num_levels", 6),
                downsample_factor=job_template_dict.get("downsample_factor", 2),
                edge_mode=job_template_dict.get("edge_mode", "crop"),
                temp_dir=job_template_dict.get("temp_dir"),
                compressionargs=job_template_dict.get("compressionargs"),
                progress_logger=progress_callback,
            )
            cleanup_warning = result.get("cleanup_warning")
            if cleanup_warning:
                m_queue.put((request_id, "progress", {
                    "message": f"Completed {filename}, but temporary cleanup failed: {cleanup_warning}",
                    "file": filename,
                    "file_idx": idx,
                    "total_files": total_files,
                    "percent": 100,
                    "overall_percent": ((idx + 1) * 100) / total_files,
                    "phase": "cleanup_warning",
                    "cleanup_warning": cleanup_warning,
                }))

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
        logging.exception("Batch conversion worker failed")
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
        self._shutdown_event = threading.Event()

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
            if self._shutdown_event.is_set():
                break

            try:
                item = self._m_queue.get(timeout=0.5)
            except Empty:
                continue  # timeout, loop back to check shutdown event
            except Exception:
                if self._shutdown_event.is_set():
                    break
                continue

            try:
                request_id, event_type, data = item
                if request_id == "__shutdown__":
                    break

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

    def _terminate_worker_processes(
        self,
        timeout_seconds: int,
        log: logging.Logger,
    ) -> None:
        """Terminate running ProcessPoolExecutor workers before teardown."""
        if self._executor is None:
            return

        processes = getattr(self._executor, "_processes", None)
        if not isinstance(processes, dict):
            return

        workers = [
            process
            for process in processes.values()
            if process is not None and process.is_alive()
        ]
        if not workers:
            return

        for process in workers:
            process.terminate()

        deadline = time.monotonic() + max(timeout_seconds, 0)
        for process in workers:
            remaining = max(0.0, deadline - time.monotonic())
            process.join(timeout=remaining)

        for process in workers:
            if not process.is_alive():
                continue
            log.warning("Worker process %s did not stop after SIGTERM; killing", process.pid)
            kill = getattr(process, "kill", None)
            if callable(kill):
                kill()
            else:
                process.terminate()
            process.join(timeout=1)

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
            "temp_dir": job_template.temp_dir,
            "compressionargs": job_template.compressionargs,
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

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------
    def shutdown(self, timeout_seconds: int = 10) -> None:
        """Gracefully stop all conversions, cancel workers, and release resources."""
        log = logging.getLogger(__name__)
        log.info("ConversionService shutdown initiated (timeout=%ds)", timeout_seconds)

        self._shutdown_event.set()

        # Cancel running futures and terminate worker processes
        if self._executor is not None:
            self._terminate_worker_processes(timeout_seconds, log)
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

        # Unblock SSE progress readers with a shutdown error event
        shutdown_error = {"error": "Server shutting down — conversion cancelled"}
        for rid, queue in list(self.progress_queues.items()):
            try:
                queue.put_nowait(("error", shutdown_error))
            except Exception:
                pass

        # Unblock the dispatch thread with a sentinel
        if self._m_queue is not None:
            try:
                self._m_queue.put(("__shutdown__", "shutdown", {}), timeout=1)
            except Exception:
                pass

        # Wait for the dispatch thread to finish
        if self._dispatcher_thread is not None and self._dispatcher_thread.is_alive():
            self._dispatcher_thread.join(timeout=timeout_seconds)

        # Tear down the multiprocessing manager
        if self._manager is not None:
            try:
                self._manager.shutdown()
            except Exception:
                pass
            self._manager = None

        self._m_queue = None
        self._dispatcher_thread = None
        self.active_jobs.clear()
        log.info("ConversionService shutdown complete")
