"""版本列表和版本详情接口。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Query

from .api_app import RECENT_RELEASE_LIMIT, _current_client, _json_error
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient
from .release_page import (
    extract_inline_release_block,
    format_release_files,
    parse_inline_ref,
    parse_release_page,
)


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_release_catalog_routes(app: FastAPI) -> None:
    specs = [
        ("/api/releases", "GET"),
        ("/api/releases/detail", "GET"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def register_release_catalog_routes(app: FastAPI) -> None:
    if getattr(app.state, "release_catalog_routes_registered", False):
        return
    app.state.release_catalog_routes_registered = True
    _remove_existing_release_catalog_routes(app)

    @app.get("/api/releases")
    def api_releases(
        project_id: str = Query(...),
        product_line: str = Query(""),
        client: RedmineClient = Depends(_current_client),
    ) -> List[Dict[str, Any]]:
        releases = ReleasePublisher(client).list_releases(project_id)
        if product_line:
            releases = [item for item in releases if item.get("product_line") == product_line]
        return releases[:RECENT_RELEASE_LIMIT]

    @app.get("/api/releases/detail")
    def api_release_detail(
        project_id: str = Query(...),
        wiki_title: str = Query(...),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        inline = parse_inline_ref(wiki_title)
        if inline:
            container_page, version_name = inline
            page = client.get_wiki_page(project_id, container_page)
            if not page:
                raise _json_error("未找到内联版本所在页面", 404)
            block = extract_inline_release_block(page.get("text", ""), version_name)
            if not block:
                raise _json_error("未找到内联版本记录", 404)
            parsed = parse_release_page(wiki_title, block)
            return {**parsed, "wiki_title": wiki_title, "container_page": container_page, "files_info": format_release_files(parsed.get("files", []))}

        page = client.get_wiki_page(project_id, wiki_title)
        if not page:
            raise _json_error("未找到版本页面", 404)
        parsed = parse_release_page(wiki_title, page.get("text", ""))
        return {**parsed, "wiki_title": wiki_title, "files_info": format_release_files(parsed.get("files", []))}
