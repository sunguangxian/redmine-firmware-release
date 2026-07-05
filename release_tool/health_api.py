"""健康检查和恢复类接口。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI

from .api_app import _current_client, _current_session, _json_error
from .config_store import db_path
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
