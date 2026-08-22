"""认证接口补强。"""

from __future__ import annotations

import time
import uuid
import os
from typing import Dict
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from .config_store import db, default_base_url
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
from .session_config import SESSION_COOKIE_SAMESITE, session_cookie_max_age, session_cookie_secure


def _set_session_cookie(response: Response, sid: str, *, remember: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=session_cookie_secure(),
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


def _login_client_key(request: Request) -> str:
    value = request.client.host if request.client else "unknown"
    return str(value or "unknown")


def _positive_env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _check_login_rate_limit(client_key: str) -> None:
    now = time.time()
    with db() as conn:
        row = conn.execute("SELECT locked_until FROM login_attempts WHERE client_key = ?", (client_key,)).fetchone()
    if row and float(row["locked_until"] or 0) > now:
        wait_seconds = max(1, int(float(row["locked_until"]) - now))
        raise _json_error(f"登录失败次数过多，请在 {wait_seconds} 秒后重试", 429)


def _record_login_failure(client_key: str) -> None:
    now = time.time()
    window = _positive_env_int("RELEASE_TOOL_LOGIN_RATE_WINDOW_SECONDS", 300, 60)
    limit = _positive_env_int("RELEASE_TOOL_LOGIN_RATE_LIMIT", 5, 2)
    with db() as conn:
        row = conn.execute("SELECT failed_count, window_started FROM login_attempts WHERE client_key = ?", (client_key,)).fetchone()
        if not row or now - float(row["window_started"] or 0) > window:
            failed_count = 1
            window_started = now
        else:
            failed_count = int(row["failed_count"] or 0) + 1
            window_started = float(row["window_started"] or now)
        locked_until = now + window if failed_count >= limit else 0
        conn.execute(
            """
            INSERT INTO login_attempts(client_key, failed_count, window_started, locked_until) VALUES(?, ?, ?, ?)
            ON CONFLICT(client_key) DO UPDATE SET failed_count=excluded.failed_count,
                window_started=excluded.window_started, locked_until=excluded.locked_until
            """,
            (client_key, failed_count, window_started, locked_until),
        )


def _clear_login_failures(client_key: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM login_attempts WHERE client_key = ?", (client_key,))


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
        "projects_checked_at": now,
    }
    sid = uuid.uuid4().hex
    SESSION_STORE.set(sid, session)
    _set_session_cookie(response, sid, remember=bool(payload.remember))
    return _public_session(session)


def register_auth_routes(app: FastAPI) -> None:
    if getattr(app.state, "auth_routes_registered", False):
        return
    app.state.auth_routes_registered = True
    @app.post("/api/auth/login", response_model=LoginResponse)
    def api_login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
        # 重新登录前先清理旧 session，避免新账号登录失败后页面继续使用旧 cookie 展示旧用户。
        _clear_request_session(request, response)
        client_key = _login_client_key(request)
        _check_login_rate_limit(client_key)
        try:
            result = _create_session_from_login(payload, response)
        except HTTPException as exc:
            if exc.status_code != 429:
                _record_login_failure(client_key)
            raise
        except RedmineError:
            _record_login_failure(client_key)
            raise
        _clear_login_failures(client_key)
        return result

    @app.post("/login")
    def api_login_form(
        request: Request,
        username: str = Form(""),
        password: str = Form(""),
        remember: bool = Form(False),
    ) -> RedirectResponse:
        response = RedirectResponse(url="/", status_code=303)
        _clear_request_session(request, response)
        client_key = _login_client_key(request)
        try:
            _check_login_rate_limit(client_key)
            _create_session_from_login(
                LoginRequest(
                    auth_mode="password",
                    username=username,
                    password=password,
                    remember=remember,
                ),
                response,
            )
        except (HTTPException, RedmineError) as exc:
            if not isinstance(exc, HTTPException) or exc.status_code != 429:
                _record_login_failure(client_key)
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            error_response = RedirectResponse(url=f"/?login_error={quote(str(detail), safe='')}", status_code=303)
            _clear_request_session(request, error_response)
            return error_response
        _clear_login_failures(client_key)
        return response

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
            SESSION_STORE.set(sid, session)
            return _public_session(session)

        _delete_session_cookie(response)
        raise _json_error("请先登录 Redmine", 401)

    @app.post("/api/auth/logout")
    def api_logout(request: Request, response: Response) -> Dict[str, bool]:
        _clear_request_session(request, response)
        return {"ok": True}
