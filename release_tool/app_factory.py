"""统一 FastAPI 应用初始化入口。"""

from __future__ import annotations

import os

from .api_app import app as app
from .audit_api import register_audit_routes
from .auth_api import register_auth_routes
from .health_api import register_health_routes
from .legacy_migration_api import register_legacy_migration_routes
from .mail_admin_test_api import register_admin_mail_test_routes
from .mail_log_api import register_mail_log_routes
from .mail_settings_api import register_mail_settings_routes
from .mail_test_api import register_mail_test_routes
from .project_api import register_project_routes
from .release_catalog_api import register_release_catalog_routes
from .release_ops_api import register_release_ops_routes
from .release_publish_api import register_release_publish_routes
from .session_guard import register_session_guard
from .wiki_config_api import register_wiki_config_routes


def move_frontend_routes_to_end() -> None:
    normal_routes = []
    frontend_routes = []
    for route in app.router.routes:
        path = getattr(route, "path", "")
        name = getattr(route, "name", "")
        if path == "/" or name == "frontend":
            frontend_routes.append(route)
        else:
            normal_routes.append(route)
    app.router.routes[:] = normal_routes + frontend_routes


def create_app():
    if getattr(app.state, "release_tool_initialized", False):
        return app
    app.state.release_tool_initialized = True

    register_auth_routes(app)
    register_audit_routes(app)
    register_session_guard(app)
    register_project_routes(app)
    register_mail_test_routes(app)
    register_admin_mail_test_routes(app)
    register_mail_settings_routes(app)
    register_mail_log_routes(app)
    register_health_routes(app)
    register_legacy_migration_routes(app)
    register_release_catalog_routes(app)
    register_release_ops_routes(app)
    register_release_publish_routes(app)
    register_wiki_config_routes(app)
    move_frontend_routes_to_end()
    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("RELEASE_TOOL_HOST", "127.0.0.1")
    port = int(os.environ.get("RELEASE_TOOL_PORT", "7860"))
    uvicorn.run("release_tool.app_factory:app", host=host, port=port, reload=False)
