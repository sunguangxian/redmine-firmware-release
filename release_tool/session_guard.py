"""会话过期与清理。"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .dependencies import SESSION_COOKIE, SESSION_STORE
from .session_config import SESSION_IDLE_SECONDS, SESSION_TTL_SECONDS


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
            session = SESSION_STORE.get(sid)
            if sid and session:
                now = time.time()
                if _expired(session, now):
                    SESSION_STORE.delete(sid)
                    response = JSONResponse(status_code=401, content={"detail": "登录会话已过期，请重新登录"})
                    response.delete_cookie(SESSION_COOKIE)
                    return response
                session["last_seen_at"] = now
        return await call_next(request)
