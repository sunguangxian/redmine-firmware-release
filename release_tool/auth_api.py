"""认证接口补强。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request, Response

from .config_store import clear_local_credentials, default_base_url, store_login
from .dependencies import (
    SESSION_COOKIE,
    SESSION_STORE,
    _current_client,
    _current_session,
    _json_error,
    _public_session,
    _user_key,
    _visible_projects_for_user,
)
from .redmine_api import RedmineClient
from .schemas import LoginRequest, LoginResponse
from .session_config import SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, session_cookie_max_age


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_auth_routes(app: FastAPI) -> None:
    specs = [
        ("/api/auth/login", "POST"),
        ("/api/auth/me", "GET"),
        ("/api/auth/logout", "POST"),
        ("/api/auth/clear-local-credentials", "POST"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def _set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
        max_age=session_cookie_max_age(),
    )


def register_auth_routes(app: FastAPI) -> None:
    if getattr(app.state, "auth_routes_registered", False):
        return
    app.state.auth_routes_registered = True
    _remove_existing_auth_routes(app)

    @app.post("/api/auth/login", response_model=LoginResponse)
    def api_login(payload: LoginRequest, response: Response) -> LoginResponse:
        base_url = default_base_url()
        auth_mode = payload.auth_mode or "password"
        username = payload.username.strip()
        api_key = payload.api_key.strip()
        if auth_mode == "api_key" and not api_key:
            raise _json_error("请填写 API Key")
        if auth_mode != "api_key" and (not username or not payload.password):
            raise _json_error("请填写用户名和密码")

        client = RedmineClient(base_url, username, payload.password, api_key=api_key, auth_mode=auth_mode)
        account = client.test_login()
        projects = client.list_projects()
        user = account.get("user", {})
        user_login = user.get("login") or username or "api-key"
        is_admin = bool(user.get("admin", False))
        projects = _visible_projects_for_user(client, projects, is_admin)
        now = time.time()
        session = {
            "connected": True,
            "base_url": base_url,
            "auth_mode": auth_mode,
            "username": username,
            "password": payload.password,
            "api_key": api_key,
            "user_login": user_login,
            "user_key": _user_key(base_url, str(user_login)),
            "is_admin": is_admin,
            "projects": projects,
            "created_at": now,
            "last_seen_at": now,
        }
        sid = uuid.uuid4().hex
        SESSION_STORE.set(sid, session)
        _set_session_cookie(response, sid)
        store_login(base_url, username, payload.password, payload.remember, auth_mode=auth_mode, api_key=api_key)
        return _public_session(session)

    @app.get("/api/auth/me", response_model=LoginResponse)
    def api_me(session: Dict[str, Any] = Depends(_current_session), client: RedmineClient = Depends(_current_client)) -> LoginResponse:
        if not session.get("is_admin"):
            session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
        return _public_session(session)

    @app.post("/api/auth/logout")
    def api_logout(request: Request, response: Response) -> Dict[str, bool]:
        sid = request.cookies.get(SESSION_COOKIE, "")
        SESSION_STORE.delete(sid)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.post("/api/auth/clear-local-credentials")
    def api_clear_local_credentials(request: Request, response: Response) -> Dict[str, bool]:
        clear_local_credentials()
        sid = request.cookies.get(SESSION_COOKIE, "")
        SESSION_STORE.delete(sid)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}
