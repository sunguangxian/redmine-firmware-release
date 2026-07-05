"""SQLite-backed legacy migration job state."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .config_store import db


def create_legacy_job(job_id: str, *, project_id: str, entry_pages: list[str], release_detail_mode: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO legacy_migration_jobs(
                id, project_id, entry_pages, release_detail_mode, status, result, error, created_at, updated_at
            ) VALUES(?, ?, ?, ?, 'running', '{}', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (job_id, project_id or "", json.dumps(entry_pages or [], ensure_ascii=False), release_detail_mode or "auto"),
        )


def append_legacy_job_log(job_id: str, message: str) -> None:
    stamped = f"{datetime.now().strftime('%H:%M:%S')} {message}"
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM legacy_migration_job_logs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        seq = int(row["next_seq"] or 1)
        conn.execute(
            """
            INSERT INTO legacy_migration_job_logs(job_id, seq, message, created_at)
            VALUES(?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (job_id, seq, stamped),
        )
        conn.execute(
            "UPDATE legacy_migration_jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (job_id,),
        )


def update_legacy_job(job_id: str, *, status: Optional[str] = None, result: Any = None, error: Optional[str] = None) -> None:
    updates: list[str] = []
    params: list[Any] = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if result is not None:
        updates.append("result = ?")
        params.append(json.dumps(result or {}, ensure_ascii=False))
    if error is not None:
        updates.append("error = ?")
        params.append(error or "")
    if not updates:
        return
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(job_id)
    with db() as conn:
        conn.execute(
            f"UPDATE legacy_migration_jobs SET {', '.join(updates)} WHERE id = ?",
            params,
        )


def legacy_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with db() as conn:
        job = conn.execute(
            "SELECT * FROM legacy_migration_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            return None
        rows = conn.execute(
            """
            SELECT message FROM legacy_migration_job_logs
            WHERE job_id = ?
            ORDER BY seq ASC
            """,
            (job_id,),
        ).fetchall()
    try:
        result = json.loads(job["result"] or "{}")
    except Exception:
        result = {}
    return {
        "job_id": job_id,
        "status": job["status"] or "running",
        "logs": [row["message"] for row in rows],
        "result": result or None,
        "error": job["error"] or "",
    }


def cleanup_legacy_jobs(days: int = 30) -> int:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM legacy_migration_jobs
            WHERE status IN ('succeeded', 'failed')
              AND updated_at < datetime('now', ?)
            """,
            (f"-{max(1, int(days or 30))} days",),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if not ids:
            return 0
        conn.executemany("DELETE FROM legacy_migration_job_logs WHERE job_id = ?", [(job_id,) for job_id in ids])
        conn.executemany("DELETE FROM legacy_migration_jobs WHERE id = ?", [(job_id,) for job_id in ids])
        return len(ids)
