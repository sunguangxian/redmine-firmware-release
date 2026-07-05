"""邮件历史查询接口。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, FastAPI, Query

from .access_control import list_visible_history
from .api_app import _current_session
from .mail_history import list_mail_history


def register_mail_log_routes(app: FastAPI) -> None:
    if getattr(app.state, "mail_log_routes_registered", False):
        return
    app.state.mail_log_routes_registered = True

    @app.get("/api/mail/history")
    def api_mail_history(
        project_id: str = Query(""),
        wiki_title: str = Query(""),
        limit: int = Query(50),
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        items = list_visible_history(
            session,
            project_id=project_id,
            wiki_title=wiki_title,
            limit=limit,
            loader=list_mail_history,
        )
        return {"ok": True, "items": items}
