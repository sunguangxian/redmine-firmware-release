"""版本发布执行历史。"""

from __future__ import annotations

import json
from typing import Any

from .config_store import db


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS release_publish_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL DEFAULT '',
            wiki_title TEXT NOT NULL DEFAULT '',
            version_name TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            release_status TEXT NOT NULL DEFAULT 'pending',
            file_status TEXT NOT NULL DEFAULT 'pending',
            wiki_status TEXT NOT NULL DEFAULT 'pending',
            index_status TEXT NOT NULL DEFAULT 'pending',
            mail_status TEXT NOT NULL DEFAULT 'skipped',
            error_message TEXT NOT NULL DEFAULT '',
            logs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_release_publish_history_lookup
            ON release_publish_history(project_id, wiki_title, created_at)
        """
    )


def create_publish_history(
    *,
    project_id: str,
    version_name: str,
    action: str,
    logs: list[str] | None = None,
) -> int:
    with db() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT INTO release_publish_history(
                project_id, version_name, action, logs, created_at, updated_at
            ) VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (project_id or "", version_name or "", action or "", json.dumps(logs or [], ensure_ascii=False)),
        )
        return int(cur.lastrowid or 0)


def update_publish_history(history_id: int, **fields: Any) -> None:
    if not history_id:
        return
    allowed = {
        "project_id",
        "wiki_title",
        "version_name",
        "action",
        "release_status",
        "file_status",
        "wiki_status",
        "index_status",
        "mail_status",
        "error_message",
        "logs",
    }
    updates: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key} = ?")
        if key == "logs":
            params.append(json.dumps(value or [], ensure_ascii=False))
        else:
            params.append(value if value is not None else "")
    if not updates:
        return
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(int(history_id))
    with db() as conn:
        _ensure_table(conn)
        conn.execute(
            f"UPDATE release_publish_history SET {', '.join(updates)} WHERE id = ?",
            params,
        )


def list_publish_history(project_id: str = "", wiki_title: str = "", limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    clauses = []
    params: list[Any] = []
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if wiki_title:
        clauses.append("wiki_title = ?")
        params.append(wiki_title)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM release_publish_history
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["logs"] = json.loads(item.get("logs") or "[]")
        except Exception:
            item["logs"] = []
        result.append(item)
    return result
