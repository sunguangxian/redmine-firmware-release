"""健康检查和恢复类接口。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI

from .api_app import _current_client, _current_session, _json_error
from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    db,
    db_path,
    get_email_server_settings,
    get_internal_contact_settings,
)
from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError


def register_health_routes(app: FastAPI) -> None:
    if getattr(app.state, "health_routes_registered", False):
        return
    app.state.health_routes_registered = True

    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        database = db_path()
        return {
            "ok": True,
            "service": "redmine-firmware-release",
            "database": str(database),
            "database_exists": database.exists(),
            "frontend_dist_exists": (Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html").exists(),
            "redmine_base_url": os.environ.get("REDMINE_BASE_URL", ""),
        }

    @app.get("/api/health/db")
    def api_health_db() -> Dict[str, Any]:
        database = db_path()
        try:
            with db() as conn:
                quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS health_check(value INTEGER)")
                conn.execute("DELETE FROM health_check")
                conn.execute("INSERT INTO health_check(value) VALUES(1)")
                value = conn.execute("SELECT value FROM health_check").fetchone()[0]
            return {
                "ok": quick_check == "ok" and value == 1,
                "database": str(database),
                "database_exists": database.exists(),
                "quick_check": quick_check,
                "writable": value == 1,
            }
        except Exception as exc:
            return {
                "ok": False,
                "database": str(database),
                "database_exists": database.exists(),
                "error": str(exc),
            }

    @app.get("/api/health/redmine")
    def api_health_redmine(
        _session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        try:
            projects = client.list_projects(membership=True)
            return {
                "ok": True,
                "base_url": client.base_url,
                "visible_project_count": len(projects),
            }
        except RedmineError as exc:
            return {"ok": False, "base_url": client.base_url, "error": str(exc)}

    @app.get("/api/health/mail-config")
    def api_health_mail_config(_session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
        internal_server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        external_server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
        internal_contacts = get_internal_contact_settings()
        internal_ready = bool(internal_server["smtp_host"] and internal_server["smtp_from"])
        external_ready = bool(external_server["smtp_host"])
        return {
            "ok": internal_ready or external_ready,
            "internal": {
                "server_configured": bool(internal_server["smtp_host"]),
                "default_sender_configured": bool(internal_server["smtp_from"]),
                "contacts_to_count": len(internal_contacts.get("contacts_to", [])),
                "contacts_cc_count": len(internal_contacts.get("contacts_cc", [])),
                "ready": internal_ready,
            },
            "external": {
                "server_configured": bool(external_server["smtp_host"]),
                "default_sender_configured": bool(external_server["smtp_from"]),
                "ready": external_ready,
            },
        }

    @app.post("/api/projects/{project_id}/rebuild-release-index")
    def api_rebuild_release_index(
        project_id: str,
        _session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        try:
            sync = IndexSync(client, project_id)
            preview = sync.preview_refresh_all()
            updated_count = sync.refresh_all()
            return {
                "ok": True,
                "updated_release_count": updated_count,
                "preview": preview,
                "message": f"已重建 Release 索引，处理 Release {updated_count} 个。",
            }
        except RedmineError as exc:
            raise _json_error(str(exc)) from exc
