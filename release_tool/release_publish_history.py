"""版本发布执行历史。"""

from __future__ import annotations

import json
from typing import Any

from .config_store import db
from .release_page import parse_inline_ref


STATUS_LABELS = {
    "pending": "未开始",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "skipped": "跳过",
    "unknown": "未知",
}

STAGE_LABELS = {
    "release_status": "Redmine 版本",
    "file_status": "附件",
    "wiki_status": "Wiki 页面",
    "index_status": "版本索引",
    "mail_status": "邮件",
}


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
            form_payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(release_publish_history)").fetchall()}
    if "form_payload" not in columns:
        conn.execute("ALTER TABLE release_publish_history ADD COLUMN form_payload TEXT NOT NULL DEFAULT '{}'")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_release_publish_history_lookup
            ON release_publish_history(project_id, wiki_title, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_release_publish_history_version_lookup
            ON release_publish_history(project_id, wiki_title, version_name, created_at)
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


def create_publish_history(
    *,
    project_id: str,
    version_name: str,
    action: str,
    logs: list[str] | None = None,
    form_payload: dict[str, Any] | None = None,
) -> int:
    with db() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT INTO release_publish_history(
                project_id, version_name, action, logs, form_payload, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                project_id or "",
                version_name or "",
                action or "",
                json.dumps(logs or [], ensure_ascii=False),
                json.dumps(form_payload or {}, ensure_ascii=False),
            ),
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
        "form_payload",
    }
    updates: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key} = ?")
        if key in {"logs", "form_payload"}:
            params.append(json.dumps(value or ([] if key == "logs" else {}), ensure_ascii=False))
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


def _status_label(status: str) -> str:
    return STATUS_LABELS.get((status or "").strip().lower(), status or "")


def _stage_summary(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for field, label in STAGE_LABELS.items():
        status = str(item.get(field) or "")
        if not status:
            continue
        parts.append(f"{label}:{_status_label(status)}")
    return "；".join(parts)


def _recover_actions(item: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if item.get("index_status") == "failed" and item.get("wiki_title"):
        actions.append({"action": "rebuild_index", "label": "重建索引"})
    if item.get("release_status") == "success" and item.get("wiki_status") != "success":
        if not (item.get("form_payload") or {}).get("has_files"):
            actions.append({"action": "continue", "label": "继续发布"})
    return actions


def _decode_row(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["logs"] = json.loads(item.get("logs") or "[]")
    except Exception:
        item["logs"] = []
    try:
        item["form_payload"] = json.loads(item.get("form_payload") or "{}")
    except Exception:
        item["form_payload"] = {}

    for field in STAGE_LABELS:
        item[f"{field}_label"] = _status_label(str(item.get(field) or ""))
    item["status_summary"] = _stage_summary(item)
    item["recover_actions"] = _recover_actions(item)
    item["can_rebuild_index"] = any(action["action"] == "rebuild_index" for action in item["recover_actions"])
    item["can_continue"] = any(action["action"] == "continue" for action in item["recover_actions"])
    return item


def get_publish_history(history_id: int) -> dict[str, Any] | None:
    with db() as conn:
        _ensure_table(conn)
        row = conn.execute("SELECT * FROM release_publish_history WHERE id = ?", (int(history_id),)).fetchone()
    return _decode_row(row) if row else None


def list_publish_history(
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
            FROM release_publish_history
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [_decode_row(row) for row in rows]
