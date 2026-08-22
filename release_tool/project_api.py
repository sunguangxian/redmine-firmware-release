"""项目与前端元信息接口。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from fastapi import Depends, FastAPI

from .config_store import MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL
from .dependencies import _current_client, _current_session
from .redmine_api import RedmineClient
from .release_page import PRODUCT_LINES
from .version import APP_VERSION


def register_project_routes(app: FastAPI) -> None:
    if getattr(app.state, "project_routes_registered", False):
        return
    app.state.project_routes_registered = True
    @app.get("/api/meta")
    def api_meta() -> Dict[str, Any]:
        return {
            "app_version": APP_VERSION,
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
        return session.get("projects", [])
