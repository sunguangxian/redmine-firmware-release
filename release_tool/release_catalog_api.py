"""版本列表和版本详情接口。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Query

from .access_control import require_project_access
from .dependencies import _current_client, _current_session, _json_error
from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError
from .release_helpers import list_release_rows
from .release_page import (
    extract_inline_release_block,
    format_release_files,
    parse_inline_ref,
    parse_release_page,
)


def _fill_configured_model(
    client: RedmineClient,
    project_id: str,
    page_title: str,
    page_text: str,
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    if parsed.get("product_line"):
        return parsed
    try:
        sync = IndexSync(client, project_id)
        profile = sync.discover_profile()
        category_key = sync._categorize(page_title, page_text, categories=profile.categories)
        category = next((item for item in profile.categories if item.key == category_key), None)
        if category:
            parsed["product_line"] = category.title or category.key
    except RedmineError:
        pass
    return parsed


def register_release_catalog_routes(app: FastAPI) -> None:
    if getattr(app.state, "release_catalog_routes_registered", False):
        return
    app.state.release_catalog_routes_registered = True
    @app.get("/api/projects/{project_id}/release-categories")
    def api_project_release_categories(
        project_id: str,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        require_project_access(session, project_id)
        try:
            profile = IndexSync(client, project_id).discover_profile()
        except RedmineError:
            return {
                "mode": "",
                "project_structure": "",
                "project_structure_label": "",
                "version_layout": "",
                "version_layout_label": "",
                "categories": [],
            }
        project_structure = "multi_model" if profile.mode == "multi_list" else "single_model"
        version_layout = profile.release_detail_mode
        return {
            "mode": profile.mode,
            "project_structure": project_structure,
            "project_structure_label": "多型号项目" if project_structure == "multi_model" else "单型号项目",
            "version_layout": version_layout,
            "version_layout_label": "所有版本一个页面" if version_layout == "inline" else "每个版本独立页面",
            "categories": [
                {"key": category.key, "title": category.title}
                for category in profile.categories
            ],
        }

    @app.get("/api/releases")
    def api_releases(
        project_id: str = Query(...),
        product_line: str = Query(""),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> List[Dict[str, Any]]:
        require_project_access(session, project_id)
        return list_release_rows(client, project_id, product_line, use_cache=True)

    @app.get("/api/releases/detail")
    def api_release_detail(
        project_id: str = Query(...),
        wiki_title: str = Query(...),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        require_project_access(session, project_id)
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
            parsed = _fill_configured_model(client, project_id, container_page, block, parsed)
            return {**parsed, "wiki_title": wiki_title, "container_page": container_page, "files_info": format_release_files(parsed.get("files", []))}

        page = client.get_wiki_page(project_id, wiki_title)
        if not page:
            raise _json_error("未找到版本页面", 404)
        parsed = parse_release_page(wiki_title, page.get("text", ""))
        parsed = _fill_configured_model(client, project_id, wiki_title, page.get("text", ""), parsed)
        return {**parsed, "wiki_title": wiki_title, "files_info": format_release_files(parsed.get("files", []))}
