"""会话与 Cookie 配置。"""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SESSION_TTL_SECONDS = _int_env("RELEASE_TOOL_SESSION_TTL_SECONDS", 28800)  # 默认 8 小时
SESSION_IDLE_SECONDS = _int_env("RELEASE_TOOL_SESSION_IDLE_SECONDS", 7200)  # 默认空闲 2 小时
SESSION_COOKIE_SECURE = _bool_env("RELEASE_TOOL_SESSION_COOKIE_SECURE", False)
SESSION_COOKIE_SAMESITE = os.environ.get("RELEASE_TOOL_SESSION_COOKIE_SAMESITE", "lax").strip().lower() or "lax"


def session_cookie_max_age() -> int:
    return min(SESSION_TTL_SECONDS, SESSION_IDLE_SECONDS)
