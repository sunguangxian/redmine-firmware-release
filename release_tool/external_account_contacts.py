"""按外网 SMTP 账号隔离外网联系人。"""

from __future__ import annotations

from typing import Any

from .config_store import (
    CONTACT_CC,
    CONTACT_TO,
    MAIL_SCOPE_EXTERNAL,
    db,
    get_user_external_email_settings,
    _get_contact_templates,
    _get_contacts,
    _replace_contact_templates,
    _replace_contacts,
    _templates_or_default,
)
from .secret_store import protect_secret

EXTERNAL_ACCOUNT_OWNER = "external_account"


def external_account_key(smtp_user: str) -> str:
    return str(smtp_user or "").strip().lower()


def _empty_contact_settings() -> dict[str, Any]:
    return {"contacts_to": [], "contacts_cc": [], "contacts_to_people": [], "contacts_cc_people": [], "contact_templates": []}


def _clean_people(items: list[dict[str, Any]] | None, fallback_emails: list[str] | None = None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    source = items if items is not None else [{"email": email, "name": ""} for email in fallback_emails or []]
    for item in source or []:
        email = str((item or {}).get("email") or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        name = str((item or {}).get("name") or "").strip() or email.split("@")[0]
        result.append({"name": name, "email": email})
    return result


def _init_external_account_contact_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_account_contact_sets (
            account_key TEXT PRIMARY KEY,
            smtp_user TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_account_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_key TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_key, contact_type, email)
        )
        """
    )


def _replace_external_people(conn: Any, account_key: str, contact_type: str, people: list[dict[str, str]]) -> None:
    conn.execute("DELETE FROM external_account_contacts WHERE account_key = ? AND contact_type = ?", (account_key, contact_type))
    conn.executemany(
        """
        INSERT INTO external_account_contacts(account_key, contact_type, name, email, display_order, updated_at)
        VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [(account_key, contact_type, item["name"], item["email"], index) for index, item in enumerate(people)],
    )


def _get_external_people(conn: Any, account_key: str, contact_type: str) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT name, email FROM external_account_contacts
        WHERE account_key = ? AND contact_type = ?
        ORDER BY display_order, id
        """,
        (account_key, contact_type),
    ).fetchall()
    return [{"name": row["name"] or str(row["email"]).split("@")[0], "email": row["email"]} for row in rows]


def _replace_external_account_contact_settings(
    conn: Any,
    *,
    smtp_user: str,
    contacts_to: list[str],
    contacts_cc: list[str],
    contacts_to_people: list[dict[str, Any]] | None = None,
    contacts_cc_people: list[dict[str, Any]] | None = None,
    contact_templates: list[dict[str, Any]] | None = None,
) -> None:
    account_key = external_account_key(smtp_user)
    if not account_key:
        return
    _init_external_account_contact_tables(conn)
    to_people = _clean_people(contacts_to_people, contacts_to)
    cc_people = _clean_people(contacts_cc_people, contacts_cc)
    contacts_to = [item["email"] for item in to_people]
    contacts_cc = [item["email"] for item in cc_people]
    conn.execute(
        """
        INSERT INTO external_account_contact_sets(account_key, smtp_user, updated_at)
        VALUES(?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(account_key) DO UPDATE SET
            smtp_user = excluded.smtp_user,
            updated_at = CURRENT_TIMESTAMP
        """,
        (account_key, str(smtp_user or "").strip()),
    )
    _replace_external_people(conn, account_key, CONTACT_TO, to_people)
    _replace_external_people(conn, account_key, CONTACT_CC, cc_people)
    _replace_contacts(conn, owner_type=EXTERNAL_ACCOUNT_OWNER, user_key=account_key, scope=MAIL_SCOPE_EXTERNAL, contact_type=CONTACT_TO, emails=contacts_to)
    _replace_contacts(conn, owner_type=EXTERNAL_ACCOUNT_OWNER, user_key=account_key, scope=MAIL_SCOPE_EXTERNAL, contact_type=CONTACT_CC, emails=contacts_cc)
    _replace_contact_templates(
        conn,
        owner_type=EXTERNAL_ACCOUNT_OWNER,
        user_key=account_key,
        scope=MAIL_SCOPE_EXTERNAL,
        templates=contact_templates if contact_templates is not None else _templates_or_default("默认", contacts_to, contacts_cc, []),
    )


def get_external_account_contact_settings(smtp_user: str) -> dict[str, Any]:
    account_key = external_account_key(smtp_user)
    if not account_key:
        return _empty_contact_settings()

    with db() as conn:
        _init_external_account_contact_tables(conn)
        to_people = _get_external_people(conn, account_key, CONTACT_TO)
        cc_people = _get_external_people(conn, account_key, CONTACT_CC)
    contacts_to = [item["email"] for item in to_people] or _get_contacts(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL, CONTACT_TO)
    contacts_cc = [item["email"] for item in cc_people] or _get_contacts(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL, CONTACT_CC)
    if not to_people:
        to_people = _clean_people(None, contacts_to)
    if not cc_people:
        cc_people = _clean_people(None, contacts_cc)
    templates = _get_contact_templates(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL)
    return {
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
        "contacts_to_people": to_people,
        "contacts_cc_people": cc_people,
        "contact_templates": _templates_or_default("默认", contacts_to, contacts_cc, templates),
    }


def get_external_account_contacts_for_user(user_key: str, smtp_user: str) -> dict[str, Any]:
    return get_external_account_contact_settings(smtp_user)


def get_user_external_email_account_settings(user_key: str) -> dict[str, Any]:
    settings = get_user_external_email_settings(user_key)
    contacts = get_external_account_contact_settings(settings.get("smtp_user", ""))
    return {**settings, **contacts}


def store_user_external_email_account_settings(
    user_key: str,
    *,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    contacts_to: list[str],
    contacts_cc: list[str],
    contacts_to_people: list[dict[str, Any]] | None = None,
    contacts_cc_people: list[dict[str, Any]] | None = None,
    contact_templates: list[dict[str, Any]] | None = None,
) -> None:
    if not user_key:
        return
    with db() as conn:
        conn.execute(
            """
            INSERT INTO user_external_email(user_key, smtp_user, smtp_password, smtp_from, updated_at)
            VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_key) DO UPDATE SET
                smtp_user = excluded.smtp_user,
                smtp_password = excluded.smtp_password,
                smtp_from = excluded.smtp_from,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_key, (smtp_user or "").strip(), protect_secret(smtp_password or ""), (smtp_from or "").strip()),
        )
        _replace_external_account_contact_settings(
            conn,
            smtp_user=smtp_user,
            contacts_to=contacts_to,
            contacts_cc=contacts_cc,
            contacts_to_people=contacts_to_people,
            contacts_cc_people=contacts_cc_people,
            contact_templates=contact_templates,
        )
