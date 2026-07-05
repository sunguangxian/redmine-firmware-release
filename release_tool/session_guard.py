"""会话过期与清理。"""

from __future__ import annotations

import os
import time
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api_app import SESSION_COOKIE, SESSIONS

SESSION_TTL_SECONDS = int(os.environ.get("RELEASE_TOOL_SESSION_TTL_SECONDS", "28800"))  # 默认 8 小时
SESSION_IDLE_SECONDS = int(os.environ.get("RELEASE_TOOL_SESSION_IDLE_SECONDS", "7200"))  # 默认空闲 2 小时


def _expired(session: dict, now: float) -> bool:
    created_at = float(session.setdefault("created_at", now))
    last_seen_at = float(session.setdefault("last_seen_at", now))
    return (now - created_at) > SESSION_TTL_SECONDS or (now - last_seen_at) > SESSION_IDLE_SECONDS


def register_session_guard(app: FastAPI) -> None:
    if getattr(app.state, "session_guard_registered", False):
        return
    app.state.session_guard_registered = True

    @app.middleware("http")
    async def session_expiration_guard(request: Request, call_next: Callable):
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/login"):
            sid = request.cookies.get(SESSION_COOKIE, "")
            session = SESSIONS.get(sid)
            if sid and session:
                now = time.time()
                if _expired(session, now):
                    SESSIONS.pop(sid, None)
                    response = JSONResponse(status_code=401, content={"detail": "登录会话已过期，请重新登录"})
                    response.delete_cookie(SESSION_COOKIE)
                    return response
                session["last_seen_at"] = now
        return await call_next(request)
