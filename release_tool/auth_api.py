"""认证接口补强。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request, Response

from .config_store import clear_local_credentials, default_base_url
from .dependencies import (
    SESSION_COOKIE,
    SESSION_STORE,
    _json_error,
    _public_session,
    _user_key,
    _visible_projects_for_user,
)
from .redmine_api import RedmineClient, RedmineError
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


def _set_session_cookie(response: Response, sid: str, *, remember: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
        max_age=session_cookie_max_age() if remember else None,
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def _clear_request_session(request: Request, response: Response) -> None:
    sid = request.cookies.get(SESSION_COOKIE, "")
    if sid:
        SESSION_STORE.delete(sid)
    _delete_session_cookie(response)


def _validate_login_payload(payload: LoginRequest) -> tuple[str, str, str, str]:
    auth_mode = payload.auth_mode or "password"
    username = payload.username.strip()
    api_key = payload.api_key.strip()
    if auth_mode == "api_key" and not api_key:
        raise _json_error("请填写 API Key")
    if auth_mode != "api_key" and (not username or not payload.password):
        raise _json_error("请填写用户名和密码")
    return default_base_url(), auth_mode, username, api_key


def _create_session_from_login(payload: LoginRequest, response: Response) -> LoginResponse:
    base_url, auth_mode, username, api_key = _validate_login_payload(payload)
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
        "remember": bool(payload.remember),
        "created_at": now,
        "last_seen_at": now,
    }
    sid = uuid.uuid4().hex
    SESSION_STORE.set(sid, session)
    _set_session_cookie(response, sid, remember=bool(payload.remember))
    return _public_session(session)


def register_auth_routes(app: FastAPI) -> None:
    if getattr(app.state, "auth_routes_registered", False):
        return
    app.state.auth_routes_registered = True
    _remove_existing_auth_routes(app)

    @app.post("/api/auth/login", response_model=LoginResponse)
    def api_login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
        # 重新登录前先清理旧 session，避免新账号登录失败后页面继续使用旧 cookie 展示旧用户。
        _clear_request_session(request, response)
        return _create_session_from_login(payload, response)

    @app.get("/api/auth/me", response_model=LoginResponse)
    def api_me(request: Request, response: Response) -> LoginResponse:
        sid = request.cookies.get(SESSION_COOKIE, "")
        session = SESSION_STORE.get(sid)
        if session and session.get("connected"):
            client = RedmineClient(
                session.get("base_url", ""),
                session.get("username", ""),
                session.get("password", ""),
                api_key=session.get("api_key", ""),
                auth_mode=session.get("auth_mode", "password"),
            )
            try:
                client.test_login()
            except RedmineError as exc:
                SESSION_STORE.delete(sid)
                _delete_session_cookie(response)
                raise _json_error(f"登录状态已失效，请重新登录：{exc}", 401) from exc
            session["last_seen_at"] = time.time()
            if not session.get("is_admin"):
                session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
            return _public_session(session)

        _delete_session_cookie(response)
        raise _json_error("请先登录 Redmine", 401)

    @app.post("/api/auth/logout")
    def api_logout(request: Request, response: Response) -> Dict[str, bool]:
        _clear_request_session(request, response)
        return {"ok": True}

    @app.post("/api/auth/clear-local-credentials")
    def api_clear_local_credentials(request: Request, response: Response) -> Dict[str, bool]:
        clear_local_credentials()
        _clear_request_session(request, response)
        return {"ok": True}
