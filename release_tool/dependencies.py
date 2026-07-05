"""FastAPI 通用依赖和会话 helper。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, HTTPException, Request

from .redmine_api import RedmineClient, RedmineError
from .session_store import InMemorySessionStore
from .schemas import LoginResponse

SESSION_COOKIE = "release_tool_session"
SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_STORE = InMemorySessionStore(SESSIONS)


def _user_key(base_url: str, login: str) -> str:
    return f"{base_url.rstrip('/')}|{login}"


def _json_error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _current_session(request: Request) -> Dict[str, Any]:
    sid = request.cookies.get(SESSION_COOKIE, "")
    session = SESSION_STORE.get(sid)
    if not session or not session.get("connected"):
        raise _json_error("请先登录 Redmine", 401)
    return session


def _current_client(session: Dict[str, Any] = Depends(_current_session)) -> RedmineClient:
    return RedmineClient(
        session.get("base_url", ""),
        session.get("username", ""),
        session.get("password", ""),
        api_key=session.get("api_key", ""),
        auth_mode=session.get("auth_mode", "password"),
    )


def _client_from_session(session: Dict[str, Any]) -> RedmineClient:
    return RedmineClient(
        session.get("base_url", ""),
        session.get("username", ""),
        session.get("password", ""),
        api_key=session.get("api_key", ""),
        auth_mode=session.get("auth_mode", "password"),
    )


def _require_admin(session: Dict[str, Any]) -> None:
    if not session.get("is_admin"):
        raise _json_error("只有 Redmine 管理员可以修改该配置", 403)


def _public_session(session: Dict[str, Any]) -> LoginResponse:
    return LoginResponse(
        connected=True,
        user_login=session.get("user_login", ""),
        is_admin=bool(session.get("is_admin")),
        projects=session.get("projects", []),
    )


def _visible_projects_for_user(client: RedmineClient, projects: List[Dict[str, Any]], is_admin: bool) -> List[Dict[str, Any]]:
    if is_admin:
        return projects
    candidates = client.list_projects(membership=True)
    visible: List[Dict[str, Any]] = []
    for project in candidates:
        identifier = str(project.get("identifier") or "")
        if not identifier:
            continue
        try:
            client.get_wiki_index(identifier)
        except RedmineError:
            continue
        visible.append(project)
    return visible
