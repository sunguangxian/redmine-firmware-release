"""内网联系人姓名存储。"""

from __future__ import annotations

from typing import Any

from .config_store import CONTACT_TO, GLOBAL_OWNER, MAIL_SCOPE_INTERNAL, db


def _init_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS named_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL,
            user_key TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_type, user_key, scope, contact_type, email)
        )
        """
    )


def _name_from_email(email: str) -> str:
    return str(email or "").split("@")[0] or str(email or "")


def clean_people(items: list[dict[str, Any]] | None, fallback_emails: list[str] | None = None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    source = items if items is not None else [{"name": "", "email": email} for email in fallback_emails or []]
    for item in source or []:
        email = str((item or {}).get("email") or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        name = str((item or {}).get("name") or "").strip() or _name_from_email(email)
        result.append({"name": name, "email": email})
    return result


def get_internal_contact_people() -> list[dict[str, str]]:
    with db() as conn:
        _init_table(conn)
        rows = conn.execute(
            """
            SELECT name, email FROM named_contacts
            WHERE owner_type = ? AND user_key = '' AND scope = ? AND contact_type = ?
            ORDER BY display_order, id
            """,
            (GLOBAL_OWNER, MAIL_SCOPE_INTERNAL, CONTACT_TO),
        ).fetchall()
    return [{"name": row["name"] or _name_from_email(row["email"]), "email": row["email"]} for row in rows]


def store_internal_contact_people(people: list[dict[str, Any]]) -> list[dict[str, str]]:
    cleaned = clean_people(people)
    with db() as conn:
        _init_table(conn)
        conn.execute(
            """
            DELETE FROM named_contacts
            WHERE owner_type = ? AND user_key = '' AND scope = ? AND contact_type = ?
            """,
            (GLOBAL_OWNER, MAIL_SCOPE_INTERNAL, CONTACT_TO),
        )
        conn.executemany(
            """
            INSERT INTO named_contacts(owner_type, user_key, scope, contact_type, name, email, display_order, updated_at)
            VALUES(?, '', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [(GLOBAL_OWNER, MAIL_SCOPE_INTERNAL, CONTACT_TO, item["name"], item["email"], index) for index, item in enumerate(cleaned)],
        )
    return cleaned
