"""Batch manifest records and JSON serialization."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from svs_to_ometiff import __version__
from svs_to_ometiff.preflight import PreflightResult


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp for manifest records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BatchManifestRecord:
    """Machine-readable result for one batch input."""

    input_path: str
    output_path: str
    status: str = "pending"
    source_width: Optional[int] = None
    source_height: Optional[int] = None
    source_mpp_x: Optional[float] = None
    source_mpp_y: Optional[float] = None
    source_compression: Optional[int] = None
    convertible: Optional[bool] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    runtime_sec: Optional[float] = None
    output_size_bytes: Optional[int] = None
    output_size_gb: Optional[float] = None
    verify_pass: Optional[bool] = None
    verify_warnings: list[str] = field(default_factory=list)
    verify_errors: list[str] = field(default_factory=list)
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    traceback_path: Optional[str] = None
    preflight_pass: Optional[bool] = None
    preflight_required_temp_gb: Optional[float] = None
    preflight_required_output_gb: Optional[float] = None
    preflight_errors: list[str] = field(default_factory=list)

    def finish(self, status: str, *, end_time: Optional[str] = None) -> None:
        """Mark the record complete and calculate runtime when possible."""
        self.status = status
        self.end_time = end_time or utc_now_iso()
        if self.start_time is None:
            return
        try:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
        except ValueError:
            return
        self.runtime_sec = round(max(0.0, (end - start).total_seconds()), 3)

    def update_from_conversion_result(self, result: dict[str, object]) -> None:
        """Populate source/output fields returned by ``convert``."""
        width = result.get("width")
        height = result.get("height")
        compression = result.get("compression")
        mpp = result.get("mpp")
        output_size = result.get("output_size_bytes")

        self.source_width = int(width) if width is not None else None
        self.source_height = int(height) if height is not None else None
        if mpp is not None:
            self.source_mpp_x = float(mpp)
            self.source_mpp_y = float(mpp)
        self.source_compression = int(compression) if compression is not None else None
        self.convertible = bool(
            result.get("convertible", self.source_compression == 33007)
        )
        if output_size is not None:
            self.output_size_bytes = int(output_size)
        else:
            out_path = Path(self.output_path)
            if out_path.exists():
                self.output_size_bytes = out_path.stat().st_size
        if self.output_size_bytes is not None:
            self.output_size_gb = self.output_size_bytes / 1e9

    def update_from_verification(self, result: dict[str, object]) -> None:
        """Populate verification fields returned by ``verify_ometiff``."""
        self.verify_pass = bool(result.get("pass"))
        self.verify_warnings = [str(item) for item in result.get("warnings", [])]
        self.verify_errors = [str(item) for item in result.get("errors", [])]

    def update_from_exception(self, exc: Exception) -> None:
        """Populate exception fields from a failed conversion step."""
        self.exception_type = type(exc).__name__
        self.exception_message = str(exc)

    def update_from_preflight(self, result: PreflightResult) -> None:
        """Populate preflight fields from a PreflightResult."""
        self.preflight_pass = result.pass_
        self.preflight_required_temp_gb = round(result.required_temp_bytes / 1e9, 3)
        self.preflight_required_output_gb = round(result.required_output_bytes / 1e9, 3)
        self.preflight_errors = result.errors
        self.source_width = result.source_width
        self.source_height = result.source_height


def write_json_manifest(
    path: str | Path,
    records: list[BatchManifestRecord],
) -> None:
    """Atomically write a JSON batch manifest."""
    manifest_path = Path(path)
    if manifest_path.suffix.lower() != ".json":
        raise ValueError("Only JSON batch manifests are currently supported")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "tool": "svs-to-ometiff-batch",
        "version": __version__,
        "generated_at": utc_now_iso(),
        "records": [asdict(record) for record in records],
    }

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=manifest_path.parent,
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(manifest_path)
