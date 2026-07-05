"""SQLite 配置与用户数据存储。"""

from __future__ import annotations

import os
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .secret_store import protect_secret, unprotect_secret

DEFAULT_REDMINE_BASE_URL = "http://192.168.1.208:3000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = ".redmine-release-tool"
DB_FILENAME = "release_tool.db"
SAVE_LOGIN_SECRETS_ENV = "RELEASE_TOOL_SAVE_LOGIN_SECRETS"

MAIL_SCOPE_INTERNAL = "internal"
MAIL_SCOPE_EXTERNAL = "external"
MAIL_SCOPES = {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL}

GLOBAL_OWNER = "global"
USER_OWNER = "user"
CONTACT_TO = "to"
CONTACT_CC = "cc"


def config_dir() -> Path:
    path = PROJECT_ROOT / LOCAL_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return config_dir() / DB_FILENAME


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS mail_servers (
            scope TEXT PRIMARY KEY,
            smtp_host TEXT NOT NULL DEFAULT '',
            smtp_port INTEGER NOT NULL DEFAULT 25,
            smtp_from TEXT NOT NULL DEFAULT '',
            use_tls INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_external_email (
            user_key TEXT PRIMARY KEY,
            smtp_user TEXT NOT NULL DEFAULT '',
            smtp_password TEXT NOT NULL DEFAULT '',
            smtp_from TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_internal_email (
            user_key TEXT PRIMARY KEY,
            smtp_user TEXT NOT NULL DEFAULT '',
            smtp_password TEXT NOT NULL DEFAULT '',
            smtp_from TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL,
            user_key TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            email TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_type, user_key, scope, contact_type, email)
        );

        CREATE INDEX IF NOT EXISTS idx_contacts_lookup
            ON contacts(owner_type, user_key, scope, contact_type, display_order, id);

        CREATE TABLE IF NOT EXISTS contact_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL,
            user_key TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL,
            name TEXT NOT NULL,
            contacts_to TEXT NOT NULL DEFAULT '[]',
            contacts_cc TEXT NOT NULL DEFAULT '[]',
            display_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_type, user_key, scope, name)
        );

        CREATE INDEX IF NOT EXISTS idx_contact_templates_lookup
            ON contact_templates(owner_type, user_key, scope, display_order, id);

        CREATE TABLE IF NOT EXISTS legacy_migration_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT '',
            entry_pages TEXT NOT NULL DEFAULT '[]',
            release_detail_mode TEXT NOT NULL DEFAULT 'auto',
            status TEXT NOT NULL DEFAULT 'running',
            result TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS legacy_migration_job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_legacy_migration_job_logs_lookup
            ON legacy_migration_job_logs(job_id, seq);
        """
    )


def default_base_url() -> str:
    return os.environ.get("REDMINE_BASE_URL", DEFAULT_REDMINE_BASE_URL).rstrip("/")


def allow_login_secret_storage() -> bool:
    return os.environ.get(SAVE_LOGIN_SECRETS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_scope(scope: str) -> str:
    value = (scope or MAIL_SCOPE_INTERNAL).strip().lower()
    return value if value in MAIL_SCOPES else MAIL_SCOPE_INTERNAL


def _normalize_contact_type(contact_type: str) -> str:
    value = (contact_type or CONTACT_TO).strip().lower()
    return value if value in {CONTACT_TO, CONTACT_CC} else CONTACT_TO


def _clean_email_list(items: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        email = str(item or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(email)
    return result


def _contact_from_email(email: str) -> dict[str, str]:
    value = str(email or "").strip()
    return {"name": value.split("@")[0] or value, "email": value}


def _clean_contact_list(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items or []:
        if isinstance(item, str):
            email = item.strip()
            name = ""
        else:
            email = str((item or {}).get("email") or "").strip()
            name = str((item or {}).get("name") or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name or email.split("@")[0], "email": email})
    return result


def _clean_template_list(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        name = str((item or {}).get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "name": name,
                "contacts_to": _clean_contact_list((item or {}).get("contacts_to") or []),
                "contacts_cc": _clean_contact_list((item or {}).get("contacts_cc") or []),
            }
        )
    return result


def _row_to_email_server(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {
            "smtp_host": "",
            "smtp_port": 25,
            "smtp_from": "",
            "use_tls": False,
        }
    return {
        "smtp_host": row["smtp_host"] or "",
        "smtp_port": int(row["smtp_port"] or 25),
        "smtp_from": row["smtp_from"] or "",
        "use_tls": bool(row["use_tls"]),
    }


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value or ""),
    )


def _delete_settings(conn: sqlite3.Connection, keys: tuple[str, ...]) -> None:
    conn.executemany("DELETE FROM app_settings WHERE key = ?", [(key,) for key in keys])


def get_saved_login() -> dict[str, Any]:
    allow_secrets = allow_login_secret_storage()
    with db() as conn:
        return {
            "base_url": _get_setting(conn, "base_url", default_base_url()) or default_base_url(),
            "auth_mode": _get_setting(conn, "auth_mode", "password") or "password",
            "username": _get_setting(conn, "username") if allow_secrets else "",
            "password": _get_setting(conn, "password") if allow_secrets else "",
            "api_key": _get_setting(conn, "api_key") if allow_secrets else "",
            "remember": (_get_setting(conn, "remember") == "1") if allow_secrets else False,
        }


def store_login(
    base_url: str,
    username: str,
    password: str,
    remember: bool,
    *,
    auth_mode: str = "password",
    api_key: str = "",
) -> None:
    with db() as conn:
        _set_setting(conn, "base_url", (base_url or default_base_url()).rstrip("/"))
        _set_setting(conn, "auth_mode", auth_mode or "password")
        if not allow_login_secret_storage():
            _set_setting(conn, "remember", "0")
            _delete_settings(conn, ("username", "password", "api_key"))
            return

        _set_setting(conn, "username", username or "")
        _set_setting(conn, "remember", "1" if remember else "0")
        if remember:
            if auth_mode == "api_key":
                _set_setting(conn, "api_key", api_key or "")
                _delete_settings(conn, ("password",))
            else:
                _set_setting(conn, "password", password or "")
                _delete_settings(conn, ("api_key",))
        else:
            _delete_settings(conn, ("password", "api_key"))


def get_email_server_settings(scope: str) -> dict[str, Any]:
    """读取管理员维护的内网/外网 SMTP 服务器配置。"""
    scope = _normalize_scope(scope)
    with db() as conn:
        row = conn.execute(
            "SELECT smtp_host, smtp_port, smtp_from, use_tls FROM mail_servers WHERE scope = ?",
            (scope,),
        ).fetchone()
    return _row_to_email_server(row)


def store_email_server_settings(
    scope: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_from: str = "",
    use_tls: bool,
) -> None:
    scope = _normalize_scope(scope)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO mail_servers(scope, smtp_host, smtp_port, smtp_from, use_tls, updated_at)
            VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope) DO UPDATE SET
                smtp_host = excluded.smtp_host,
                smtp_port = excluded.smtp_port,
                smtp_from = excluded.smtp_from,
                use_tls = excluded.use_tls,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                scope,
                (smtp_host or "").strip(),
                int(smtp_port or 25),
                (smtp_from or "").strip(),
                1 if use_tls else 0,
            ),
        )


def _get_contacts(owner_type: str, user_key: str, scope: str, contact_type: str) -> list[str]:
    scope = _normalize_scope(scope)
    contact_type = _normalize_contact_type(contact_type)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT email
            FROM contacts
            WHERE owner_type = ? AND user_key = ? AND scope = ? AND contact_type = ?
            ORDER BY display_order ASC, id ASC
            """,
            (owner_type, user_key or "", scope, contact_type),
        ).fetchall()
    return [str(row["email"]) for row in rows]


def _replace_contacts(
    conn: sqlite3.Connection,
    *,
    owner_type: str,
    user_key: str,
    scope: str,
    contact_type: str,
    emails: list[str],
) -> None:
    scope = _normalize_scope(scope)
    contact_type = _normalize_contact_type(contact_type)
    user_key = user_key or ""
    conn.execute(
        """
        DELETE FROM contacts
        WHERE owner_type = ? AND user_key = ? AND scope = ? AND contact_type = ?
        """,
        (owner_type, user_key, scope, contact_type),
    )
    for idx, email in enumerate(_clean_email_list(emails)):
        conn.execute(
            """
            INSERT INTO contacts(owner_type, user_key, scope, contact_type, email, display_order)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (owner_type, user_key, scope, contact_type, email, idx),
        )


def _get_contact_templates(owner_type: str, user_key: str, scope: str) -> list[dict[str, Any]]:
    scope = _normalize_scope(scope)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT name, contacts_to, contacts_cc
            FROM contact_templates
            WHERE owner_type = ? AND user_key = ? AND scope = ?
            ORDER BY display_order ASC, id ASC
            """,
            (owner_type, user_key or "", scope),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            contacts_to = json.loads(row["contacts_to"] or "[]")
            contacts_cc = json.loads(row["contacts_cc"] or "[]")
        except json.JSONDecodeError:
            contacts_to = []
            contacts_cc = []
        result.append(
            {
                "name": row["name"] or "",
                "contacts_to": _clean_contact_list(contacts_to),
                "contacts_cc": _clean_contact_list(contacts_cc),
            }
        )
    return result


def _replace_contact_templates(
    conn: sqlite3.Connection,
    *,
    owner_type: str,
    user_key: str,
    scope: str,
    templates: list[dict[str, Any]],
) -> None:
    scope = _normalize_scope(scope)
    user_key = user_key or ""
    conn.execute(
        """
        DELETE FROM contact_templates
        WHERE owner_type = ? AND user_key = ? AND scope = ?
        """,
        (owner_type, user_key, scope),
    )
    for idx, item in enumerate(_clean_template_list(templates)):
        conn.execute(
            """
            INSERT INTO contact_templates(owner_type, user_key, scope, name, contacts_to, contacts_cc, display_order, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                owner_type,
                user_key,
                scope,
                item["name"],
                json.dumps(item["contacts_to"], ensure_ascii=False),
                json.dumps(item["contacts_cc"], ensure_ascii=False),
                idx,
            ),
        )


def _templates_or_default(name: str, contacts_to: list[str], contacts_cc: list[str], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if templates:
        return templates
    if contacts_to or contacts_cc:
        return [
            {
                "name": name,
                "contacts_to": [_contact_from_email(email) for email in _clean_email_list(contacts_to)],
                "contacts_cc": [_contact_from_email(email) for email in _clean_email_list(contacts_cc)],
            }
        ]
    return []


def get_internal_contact_settings() -> dict[str, Any]:
    contacts_to = _get_contacts(GLOBAL_OWNER, "", MAIL_SCOPE_INTERNAL, CONTACT_TO)
    contacts_cc = _get_contacts(GLOBAL_OWNER, "", MAIL_SCOPE_INTERNAL, CONTACT_CC)
    return {
        "contacts": _clean_email_list([*contacts_to, *contacts_cc]),
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
    }


def store_internal_contact_settings(
    *,
    contacts: list[str] | None = None,
    contacts_to: list[str] | None = None,
    contacts_cc: list[str] | None = None,
) -> None:
    if contacts is not None:
        contacts_to = contacts
        contacts_cc = []
    with db() as conn:
        _replace_contacts(
            conn,
            owner_type=GLOBAL_OWNER,
            user_key="",
            scope=MAIL_SCOPE_INTERNAL,
            contact_type=CONTACT_TO,
            emails=contacts_to or [],
        )
        _replace_contacts(
            conn,
            owner_type=GLOBAL_OWNER,
            user_key="",
            scope=MAIL_SCOPE_INTERNAL,
            contact_type=CONTACT_CC,
            emails=contacts_cc or [],
        )


def get_user_internal_email_settings(user_key: str) -> dict[str, Any]:
    if not user_key:
        return {
            "smtp_user": "",
            "smtp_password": "",
            "smtp_from": "",
            "contacts_to": [],
            "contacts_cc": [],
            "contact_templates": [],
        }
    with db() as conn:
        row = conn.execute(
            """
            SELECT smtp_user, smtp_password, smtp_from
            FROM user_internal_email
            WHERE user_key = ?
            """,
            (user_key,),
        ).fetchone()
    if row is None:
        smtp_user = ""
        smtp_password = ""
        smtp_from = ""
    else:
        smtp_user = row["smtp_user"] or ""
        smtp_password = row["smtp_password"] or ""
        smtp_from = row["smtp_from"] or ""
    return {
        "smtp_user": smtp_user,
        "smtp_password": unprotect_secret(smtp_password),
        "smtp_from": smtp_from,
        "contacts_to": _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_INTERNAL, CONTACT_TO),
        "contacts_cc": _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_INTERNAL, CONTACT_CC),
        "contact_templates": _templates_or_default(
            "默认",
            _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_INTERNAL, CONTACT_TO),
            _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_INTERNAL, CONTACT_CC),
            _get_contact_templates(USER_OWNER, user_key, MAIL_SCOPE_INTERNAL),
        ),
    }


def store_user_internal_email_settings(
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
            INSERT INTO user_internal_email(user_key, smtp_user, smtp_password, smtp_from, updated_at)
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
        _replace_contacts(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_INTERNAL,
            contact_type=CONTACT_TO,
            emails=contacts_to,
        )
        _replace_contacts(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_INTERNAL,
            contact_type=CONTACT_CC,
            emails=contacts_cc,
        )
        _replace_contact_templates(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_INTERNAL,
            templates=contact_templates if contact_templates is not None else _templates_or_default("默认", contacts_to, contacts_cc, []),
        )


def get_user_external_email_settings(user_key: str) -> dict[str, Any]:
    if not user_key:
        return {
            "smtp_user": "",
            "smtp_password": "",
            "smtp_from": "",
            "contacts_to": [],
            "contacts_cc": [],
            "contact_templates": [],
        }
    with db() as conn:
        row = conn.execute(
            """
            SELECT smtp_user, smtp_password, smtp_from
            FROM user_external_email
            WHERE user_key = ?
            """,
            (user_key,),
        ).fetchone()
    if row is None:
        smtp_user = ""
        smtp_password = ""
        smtp_from = ""
    else:
        smtp_user = row["smtp_user"] or ""
        smtp_password = row["smtp_password"] or ""
        smtp_from = row["smtp_from"] or ""
    contacts_to = _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_EXTERNAL, CONTACT_TO)
    contacts_cc = _get_contacts(USER_OWNER, user_key, MAIL_SCOPE_EXTERNAL, CONTACT_CC)
    return {
        "smtp_user": smtp_user,
        "smtp_password": unprotect_secret(smtp_password),
        "smtp_from": smtp_from,
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
        "contact_templates": _templates_or_default(
            "默认",
            contacts_to,
            contacts_cc,
            _get_contact_templates(USER_OWNER, user_key, MAIL_SCOPE_EXTERNAL),
        ),
    }


def store_user_external_email_settings(
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
        _replace_contacts(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_EXTERNAL,
            contact_type=CONTACT_TO,
            emails=contacts_to,
        )
        _replace_contacts(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_EXTERNAL,
            contact_type=CONTACT_CC,
            emails=contacts_cc,
        )
        _replace_contact_templates(
            conn,
            owner_type=USER_OWNER,
            user_key=user_key,
            scope=MAIL_SCOPE_EXTERNAL,
            templates=contact_templates if contact_templates is not None else _templates_or_default("默认", contacts_to, contacts_cc, []),
        )


def get_email_settings() -> dict[str, Any]:
    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    contacts = get_internal_contact_settings()
    return {
        "smtp_host": server["smtp_host"],
        "smtp_port": server["smtp_port"],
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": server["smtp_from"],
        "use_tls": server["use_tls"],
        "contacts_to": contacts["contacts_to"],
        "contacts_cc": contacts["contacts_cc"],
    }


def get_user_email_settings(user_key: str) -> dict[str, Any]:
    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    email = get_user_external_email_settings(user_key)
    return {
        "smtp_host": server["smtp_host"],
        "smtp_port": server["smtp_port"],
        "smtp_user": email["smtp_user"],
        "smtp_password": email["smtp_password"],
        "smtp_from": email["smtp_from"] or server["smtp_from"],
        "use_tls": server["use_tls"],
        "contacts_to": email["contacts_to"],
        "contacts_cc": email["contacts_cc"],
    }


def store_email_settings(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    use_tls: bool,
    contacts_to: list[str],
    contacts_cc: list[str],
) -> None:
    store_email_server_settings(
        MAIL_SCOPE_EXTERNAL,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_from=smtp_from,
        use_tls=use_tls,
    )
    store_internal_contact_settings(contacts_to=contacts_to, contacts_cc=contacts_cc)


def store_user_email_settings(
    user_key: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    use_tls: bool,
    contacts_to: list[str],
    contacts_cc: list[str],
) -> None:
    store_user_external_email_settings(
        user_key,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        contacts_to=contacts_to,
        contacts_cc=contacts_cc,
    )


def get_last_project() -> str:
    with db() as conn:
        return _get_setting(conn, "last_project", "")


def set_last_project(project_id: str) -> None:
    with db() as conn:
        _set_setting(conn, "last_project", project_id or "")
