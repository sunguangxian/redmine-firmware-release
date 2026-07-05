"""邮件发送历史记录。"""

from __future__ import annotations

import json
from typing import Any

from .config_store import db
from .release_page import parse_inline_ref


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_send_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL DEFAULT '',
            wiki_title TEXT NOT NULL DEFAULT '',
            version_name TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            to_addrs TEXT NOT NULL DEFAULT '[]',
            cc_addrs TEXT NOT NULL DEFAULT '[]',
            attachment_count INTEGER NOT NULL DEFAULT 0,
            sender_user TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            send_type TEXT NOT NULL DEFAULT 'publish',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mail_send_history_lookup
            ON mail_send_history(project_id, wiki_title, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mail_send_history_version_lookup
            ON mail_send_history(project_id, wiki_title, version_name, created_at)
        """
    )


def _wiki_title_candidates(wiki_title: str) -> list[str]:
    value = (wiki_title or "").strip()
    if not value:
        return []
    result = [value]
    inline = parse_inline_ref(value)
    if inline and inline[0] not in result:
        result.append(inline[0])
    return result


def record_mail_send(
    *,
    project_id: str,
    wiki_title: str,
    version_name: str = "",
    scope: str,
    subject: str,
    to_addrs: list[str],
    cc_addrs: list[str],
    attachment_count: int,
    sender_user: str,
    status: str,
    error_message: str = "",
    send_type: str = "publish",
) -> int:
    with db() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT INTO mail_send_history(
                project_id, wiki_title, version_name, scope, subject,
                to_addrs, cc_addrs, attachment_count, sender_user,
                status, error_message, send_type, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                project_id or "",
                wiki_title or "",
                version_name or "",
                scope or "",
                subject or "",
                json.dumps(to_addrs or [], ensure_ascii=False),
                json.dumps(cc_addrs or [], ensure_ascii=False),
                int(attachment_count or 0),
                sender_user or "",
                status or "",
                error_message or "",
                send_type or "publish",
            ),
        )
        return int(cur.lastrowid or 0)


def list_mail_history(
    project_id: str = "",
    wiki_title: str = "",
    version_name: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    clauses = []
    params: list[Any] = []
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    title_candidates = _wiki_title_candidates(wiki_title)
    if title_candidates:
        placeholders = ",".join("?" for _ in title_candidates)
        clauses.append(f"wiki_title IN ({placeholders})")
        params.extend(title_candidates)
    if version_name:
        clauses.append("version_name = ?")
        params.append(version_name)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM mail_send_history
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("to_addrs", "cc_addrs"):
            try:
                item[key] = json.loads(item.get(key) or "[]")
            except Exception:
                item[key] = []
        result.append(item)
    return result
