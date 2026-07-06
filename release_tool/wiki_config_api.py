"""Wiki 发布结构配置接口。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .audit_log import record_audit
from .dependencies import _current_client, _current_session, _json_error, _require_admin
from .index_sync import IndexSync
from .redmine_api import RedmineClient
from .release_helpers import invalidate_release_rows
from .release_mode_converter import ReleaseModeConverter
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text


class WikiConfigSaveRequest(BaseModel):
    text: str = ""


class WikiConfigCheckRequest(BaseModel):
    text: str = ""


class WikiConfigGenerateRequest(BaseModel):
    project_id: str
    template_key: str = "single_list"


class WikiModeConvertRequest(BaseModel):
    target_mode: str


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_wiki_config_routes(app: FastAPI) -> None:
    specs = [
        ("/api/wiki-config/templates", "GET"),
        ("/api/wiki-config/generate", "POST"),
        ("/api/wiki-config/check", "POST"),
        ("/api/wiki-config/{project_id}/refresh-preview", "GET"),
        ("/api/wiki-config/{project_id}/refresh", "POST"),
        ("/api/wiki-config/{project_id}/convert-preview", "POST"),
        ("/api/wiki-config/{project_id}/convert", "POST"),
        ("/api/wiki-config/{project_id}", "GET"),
        ("/api/wiki-config/{project_id}", "PUT"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def register_wiki_config_routes(app: FastAPI) -> None:
    if getattr(app.state, "wiki_config_routes_registered", False):
        return
    app.state.wiki_config_routes_registered = True
    _remove_existing_wiki_config_routes(app)

    @app.get("/api/wiki-config/templates")
    def api_wiki_templates(session: Dict[str, Any] = Depends(_current_session)) -> List[Any]:
        _require_admin(session)
        return TEMPLATE_CHOICES

    @app.post("/api/wiki-config/generate")
    def api_generate_wiki_config(
        payload: WikiConfigGenerateRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, str]:
        _require_admin(session)
        text = build_config_template(payload.template_key or "single_list", payload.project_id)
        ok, msg = validate_config_text(text)
        return {"text": text, "message": msg if ok else msg}

    @app.post("/api/wiki-config/check")
    def api_check_wiki_config(
        payload: WikiConfigCheckRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        _require_admin(session)
        ok, msg = validate_config_text(payload.text or "")
        return {"ok": ok, "message": msg}

    @app.get("/api/wiki-config/{project_id}/refresh-preview")
    def api_preview_wiki_refresh(
        project_id: str,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_admin(session)
        return IndexSync(client, project_id).preview_refresh_all()

    @app.post("/api/wiki-config/{project_id}/refresh")
    def api_refresh_wiki_index(
        project_id: str,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_admin(session)
        sync = IndexSync(client, project_id)
        preview = sync.preview_refresh_all()
        updated_count = sync.refresh_all()
        invalidate_release_rows(project_id)
        return {
            "ok": True,
            "updated_release_count": updated_count,
            "preview": preview,
            "message": f"已按当前 Release_Tool_Config 重建索引，处理 Release {updated_count} 个。",
        }

    @app.post("/api/wiki-config/{project_id}/convert-preview")
    def api_preview_release_mode_convert(
        project_id: str,
        payload: WikiModeConvertRequest,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_admin(session)
        return ReleaseModeConverter(client, project_id).preview(payload.target_mode)

    @app.post("/api/wiki-config/{project_id}/convert")
    def api_release_mode_convert(
        project_id: str,
        payload: WikiModeConvertRequest,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_admin(session)
        result = ReleaseModeConverter(client, project_id).convert(payload.target_mode)
        invalidate_release_rows(project_id)
        record_audit(
            actor=session.get("user_login", ""),
            action="wiki_release_mode_converted",
            target_type="wiki_config",
            target_id=project_id,
            details={
                "current_mode": result.get("current_mode"),
                "target_mode": result.get("target_mode"),
                "converted_count": result.get("converted_count"),
            },
        )
        return result

    @app.get("/api/wiki-config/{project_id}")
    def api_get_wiki_config(
        project_id: str,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, str]:
        _require_admin(session)
        page = client.get_wiki_page(project_id, CONFIG_PAGE_TITLE)
        if not page:
            return {"text": "", "message": f"未找到 {CONFIG_PAGE_TITLE}"}
        text = page.get("text", "")
        ok, msg = validate_config_text(text)
        return {"text": text, "message": msg if ok else f"已读取，但{msg}"}

    @app.put("/api/wiki-config/{project_id}")
    def api_save_wiki_config(
        project_id: str,
        payload: WikiConfigSaveRequest,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, str]:
        _require_admin(session)
        ok, msg = validate_config_text(payload.text or "")
        if not ok:
            raise _json_error(msg)
        client.put_wiki_page(project_id, CONFIG_PAGE_TITLE, payload.text, "release tool config update")
        invalidate_release_rows(project_id)
        record_audit(
            actor=session.get("user_login", ""),
            action="wiki_config_updated",
            target_type="wiki_config",
            target_id=project_id,
            details={"message": msg, "text_length": len(payload.text or "")},
        )
        return {"message": f"已保存到 {CONFIG_PAGE_TITLE}。{msg}"}
