"""Audit log storage for local configuration and migration operations."""

from __future__ import annotations

import json
from typing import Any

from .config_store import db


def record_audit(
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str = "",
    details: dict[str, Any] | None = None,
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_logs(actor, action, target_type, target_id, details, created_at)
            VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                actor or "",
                action or "",
                target_type or "",
                target_id or "",
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)


def list_audit_logs(limit: int = 200) -> list[dict[str, Any]]:
    safe_limit = min(500, max(1, int(limit or 200)))
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, actor, action, target_type, target_id, details, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            details = json.loads(row["details"] or "{}")
        except Exception:
            details = {}
        result.append(
            {
                "id": row["id"],
                "actor": row["actor"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "details": details,
                "created_at": row["created_at"],
            }
        )
    return result
