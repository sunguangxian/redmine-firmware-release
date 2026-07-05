"""项目与前端元信息接口。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from fastapi import Depends, FastAPI

from .api_app import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    _current_client,
    _current_session,
    _visible_projects_for_user,
)
from .redmine_api import RedmineClient
from .release_page import PRODUCT_LINES


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_project_routes(app: FastAPI) -> None:
    specs = [
        ("/api/meta", "GET"),
        ("/api/projects", "GET"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def register_project_routes(app: FastAPI) -> None:
    if getattr(app.state, "project_routes_registered", False):
        return
    app.state.project_routes_registered = True
    _remove_existing_project_routes(app)

    @app.get("/api/meta")
    def api_meta() -> Dict[str, Any]:
        return {
            "product_lines": list(PRODUCT_LINES.keys()),
            "mail_scopes": [
                {"label": "内网邮件", "value": MAIL_SCOPE_INTERNAL},
                {"label": "外网邮件", "value": MAIL_SCOPE_EXTERNAL},
            ],
            "today": date.today().isoformat(),
        }

    @app.get("/api/projects")
    def api_projects(
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> List[Dict[str, Any]]:
        if not session.get("is_admin"):
            session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
        return session.get("projects", [])
