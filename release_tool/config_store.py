"""本地配置与凭据存储。"""

from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any

DEFAULT_REDMINE_BASE_URL = "http://192.168.1.208:3000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = ".redmine-release-tool"
SAVE_LOGIN_SECRETS_ENV = "RELEASE_TOOL_SAVE_LOGIN_SECRETS"


def config_dir() -> Path:
    path = PROJECT_ROOT / LOCAL_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return config_dir() / "settings.json"


def user_settings_dir() -> Path:
    path = config_dir() / "users"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_settings_path(user_key: str) -> Path:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()
    return user_settings_dir() / f"{digest}.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_user_settings(user_key: str) -> dict[str, Any]:
    if not user_key:
        return {}
    path = user_settings_path(user_key)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_user_settings(user_key: str, data: dict[str, Any]) -> None:
    if not user_key:
        return
    path = user_settings_path(user_key)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def default_base_url() -> str:
    return os.environ.get("REDMINE_BASE_URL", DEFAULT_REDMINE_BASE_URL).rstrip("/")


def allow_login_secret_storage() -> bool:
    return os.environ.get(SAVE_LOGIN_SECRETS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def get_saved_login() -> dict[str, Any]:
    data = load_settings()
    allow_secrets = allow_login_secret_storage()
    return {
        "base_url": data.get("base_url") or default_base_url(),
        "auth_mode": data.get("auth_mode", "password"),
        "username": data.get("username", "") if allow_secrets else "",
        "password": data.get("password", "") if allow_secrets else "",
        "api_key": data.get("api_key", "") if allow_secrets else "",
        "remember": bool(data.get("remember", False)) if allow_secrets else False,
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
    data = load_settings()
    data["base_url"] = base_url.rstrip("/")
    data["auth_mode"] = auth_mode
    if not allow_login_secret_storage():
        data["remember"] = False
        data.pop("username", None)
        data.pop("password", None)
        data.pop("api_key", None)
        save_settings(data)
        return
    data["username"] = username
    if remember:
        data["remember"] = True
        if auth_mode == "api_key":
            data["api_key"] = api_key
            data.pop("password", None)
        else:
            data["password"] = password
            data.pop("api_key", None)
    else:
        data["remember"] = False
        data.pop("password", None)
        data.pop("api_key", None)
    save_settings(data)


def get_email_settings() -> dict[str, Any]:
    data = load_settings()
    email = data.get("email") or {}
    return _normalize_email_settings(email)


def get_user_email_settings(user_key: str) -> dict[str, Any]:
    data = load_user_settings(user_key)
    email = data.get("email") or {}
    return _normalize_email_settings(email)


def _normalize_email_settings(email: dict[str, Any]) -> dict[str, Any]:
    return {
        "smtp_host": email.get("smtp_host", ""),
        "smtp_port": int(email.get("smtp_port") or 25),
        "smtp_user": email.get("smtp_user", ""),
        "smtp_password": email.get("smtp_password", ""),
        "smtp_from": email.get("smtp_from", ""),
        "use_tls": bool(email.get("use_tls", False)),
        "contacts_to": email.get("contacts_to", []),
        "contacts_cc": email.get("contacts_cc", []),
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
    data = load_settings()
    data["email"] = {
        "smtp_host": (smtp_host or "").strip(),
        "smtp_port": int(smtp_port or 25),
        "smtp_user": (smtp_user or "").strip(),
        "smtp_password": smtp_password or "",
        "smtp_from": (smtp_from or "").strip(),
        "use_tls": bool(use_tls),
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
    }
    save_settings(data)


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
    data = load_user_settings(user_key)
    data["email"] = {
        "smtp_host": (smtp_host or "").strip(),
        "smtp_port": int(smtp_port or 25),
        "smtp_user": (smtp_user or "").strip(),
        "smtp_password": smtp_password or "",
        "smtp_from": (smtp_from or "").strip(),
        "use_tls": bool(use_tls),
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
    }
    save_user_settings(user_key, data)


def get_last_project() -> str:
    return load_settings().get("last_project", "")


def set_last_project(project_id: str) -> None:
    data = load_settings()
    data["last_project"] = project_id
    save_settings(data)
