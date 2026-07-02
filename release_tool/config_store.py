"""本地配置与凭据存储。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "redmine-release-tool"
DEFAULT_REDMINE_BASE_URL = "http://192.168.1.208:3000"


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return config_dir() / "settings.json"


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


def default_base_url() -> str:
    return os.environ.get("REDMINE_BASE_URL", DEFAULT_REDMINE_BASE_URL).rstrip("/")


def get_saved_login() -> dict[str, Any]:
    data = load_settings()
    return {
        "base_url": data.get("base_url") or default_base_url(),
        "auth_mode": data.get("auth_mode", "password"),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
        "api_key": data.get("api_key", ""),
        "remember": bool(data.get("remember", True)),
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


def get_last_project() -> str:
    return load_settings().get("last_project", "")


def set_last_project(project_id: str) -> None:
    data = load_settings()
    data["last_project"] = project_id
    save_settings(data)
