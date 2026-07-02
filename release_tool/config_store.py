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


def get_saved_login() -> dict[str, str]:
    data = load_settings()
    return {
        "base_url": data.get("base_url") or default_base_url(),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
        "remember": bool(data.get("remember", True)),
    }


def store_login(base_url: str, username: str, password: str, remember: bool) -> None:
    data = load_settings()
    data["base_url"] = base_url.rstrip("/")
    data["username"] = username
    if remember:
        data["password"] = password
        data["remember"] = True
    else:
        data.pop("password", None)
        data["remember"] = False
    save_settings(data)


def get_last_project() -> str:
    return load_settings().get("last_project", "")


def set_last_project(project_id: str) -> None:
    data = load_settings()
    data["last_project"] = project_id
    save_settings(data)
