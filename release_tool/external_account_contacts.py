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
    return {"contacts_to": [], "contacts_cc": [], "contact_templates": []}


def _contact_settings_part(settings: dict[str, Any] | None) -> dict[str, Any]:
    if not settings:
        return _empty_contact_settings()
    return {
        "contacts_to": settings.get("contacts_to", []) or [],
        "contacts_cc": settings.get("contacts_cc", []) or [],
        "contact_templates": settings.get("contact_templates", []) or [],
    }


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


def _external_account_contact_set_exists(conn: Any, account_key: str) -> bool:
    _init_external_account_contact_tables(conn)
    row = conn.execute(
        "SELECT account_key FROM external_account_contact_sets WHERE account_key = ?",
        (account_key,),
    ).fetchone()
    return row is not None


def _replace_external_account_contact_settings(
    conn: Any,
    *,
    smtp_user: str,
    contacts_to: list[str],
    contacts_cc: list[str],
    contact_templates: list[dict[str, Any]] | None = None,
) -> None:
    account_key = external_account_key(smtp_user)
    if not account_key:
        return
    _init_external_account_contact_tables(conn)
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
    _replace_contacts(
        conn,
        owner_type=EXTERNAL_ACCOUNT_OWNER,
        user_key=account_key,
        scope=MAIL_SCOPE_EXTERNAL,
        contact_type=CONTACT_TO,
        emails=contacts_to,
    )
    _replace_contacts(
        conn,
        owner_type=EXTERNAL_ACCOUNT_OWNER,
        user_key=account_key,
        scope=MAIL_SCOPE_EXTERNAL,
        contact_type=CONTACT_CC,
        emails=contacts_cc,
    )
    _replace_contact_templates(
        conn,
        owner_type=EXTERNAL_ACCOUNT_OWNER,
        user_key=account_key,
        scope=MAIL_SCOPE_EXTERNAL,
        templates=contact_templates if contact_templates is not None else _templates_or_default("默认", contacts_to, contacts_cc, []),
    )


def get_external_account_contact_settings(
    smtp_user: str,
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    account_key = external_account_key(smtp_user)
    default = _contact_settings_part(fallback)
    if not account_key:
        return default

    with db() as conn:
        exists = _external_account_contact_set_exists(conn, account_key)
    if not exists:
        return default

    contacts_to = _get_contacts(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL, CONTACT_TO)
    contacts_cc = _get_contacts(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL, CONTACT_CC)
    templates = _get_contact_templates(EXTERNAL_ACCOUNT_OWNER, account_key, MAIL_SCOPE_EXTERNAL)
    return {
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
        "contact_templates": _templates_or_default("默认", contacts_to, contacts_cc, templates),
    }


def get_external_account_contacts_for_user(user_key: str, smtp_user: str) -> dict[str, Any]:
    saved = get_user_external_email_settings(user_key)
    saved_account_key = external_account_key(saved.get("smtp_user", ""))
    account_key = external_account_key(smtp_user)
    fallback = _contact_settings_part(saved) if account_key and account_key == saved_account_key else _empty_contact_settings()
    return get_external_account_contact_settings(smtp_user, fallback=fallback)


def get_user_external_email_account_settings(user_key: str) -> dict[str, Any]:
    settings = get_user_external_email_settings(user_key)
    contacts = get_external_account_contact_settings(settings.get("smtp_user", ""), fallback=_contact_settings_part(settings))
    return {**settings, **contacts}


def store_user_external_email_account_settings(
    user_key: str,
    *,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    contacts_to: list[str],
    contacts_cc: list[str],
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
            (
                user_key,
                (smtp_user or "").strip(),
                protect_secret(smtp_password or ""),
                (smtp_from or "").strip(),
            ),
        )
        _replace_external_account_contact_settings(
            conn,
            smtp_user=smtp_user,
            contacts_to=contacts_to,
            contacts_cc=contacts_cc,
            contact_templates=contact_templates,
        )
