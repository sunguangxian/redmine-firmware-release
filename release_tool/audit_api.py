"""Audit log API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, FastAPI, Query

from .api_app import _current_session, _require_admin
from .audit_log import list_audit_logs


def register_audit_routes(app: FastAPI) -> None:
    if getattr(app.state, "audit_routes_registered", False):
        return
    app.state.audit_routes_registered = True

    @app.get("/api/audit-log")
    def api_audit_log(
        limit: int = Query(200),
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        _require_admin(session)
        return {"ok": True, "items": list_audit_logs(limit)}
