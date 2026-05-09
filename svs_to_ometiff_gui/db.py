"""Database management for persistent conversion jobs.

Uses standard library sqlite3 to store job history, preventing state loss
during server restarts and enabling robust background processing.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobDB:
    """Manages the SQLite database for job persistence."""

    def __init__(self, db_path: str = "jobs.sqlite3"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,      -- 'single' or 'batch'
                    status TEXT NOT NULL,        -- 'pending', 'running', 'completed', 'error'
                    input_path TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    percent REAL DEFAULT 0.0,
                    phase TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
            # Requeue any jobs that were running when the server died
            conn.execute(
                "UPDATE jobs SET status = 'error', error = 'Server crashed during processing' WHERE status IN ('pending', 'running')"
            )

    def create_job(self, job_id: str, job_type: str, input_path: str, output_path: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, job_type, status, input_path, output_path, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?, ?, ?)
                """,
                (job_id, job_type, input_path, output_path, now, now),
            )

    def update_job_progress(self, job_id: str, percent: float, phase: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE jobs 
                SET status = 'running', percent = ?, phase = ?, updated_at = ?
                WHERE id = ?
                """,
                (percent, phase, now, job_id),
            )

    def mark_job_completed(self, job_id: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'completed', percent = 100.0, phase = 'complete', updated_at = ? WHERE id = ?",
                (now, job_id),
            )

    def mark_job_error(self, job_id: str, error: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'error', error = ?, updated_at = ? WHERE id = ?",
                (error, now, job_id),
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row:
                return dict(row)
            return None

    def get_recent_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            cur = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]
