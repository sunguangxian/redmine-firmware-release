from release_tool.api_app import app, main
from release_tool.health_api import register_health_routes
from release_tool.index_sync_patch import apply_index_sync_patches
from release_tool.mail_test_api import register_mail_test_routes
from release_tool.release_ops_api import register_release_ops_routes
from release_tool.secure_config import apply_secure_config_patches
from release_tool.session_guard import register_session_guard


def move_frontend_routes_to_end():
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


apply_secure_config_patches()
apply_index_sync_patches()
register_session_guard(app)
register_mail_test_routes(app)
register_health_routes(app)
register_release_ops_routes(app)
move_frontend_routes_to_end()

if __name__ == "__main__":
    main()
