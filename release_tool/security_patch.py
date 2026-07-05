"""安全相关路由覆盖。

集中修补早期接口的权限边界：
- Wiki 结构管理接口只允许 Redmine 管理员调用。
- 发布/邮件历史只返回当前用户可访问项目的数据。
- 历史恢复操作先检查记录对应项目是否可访问。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .api_app import _current_client, _current_session, _json_error, _require_admin
from .index_sync import IndexSync
from .mail_history import list_mail_history
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, proj_tag_from_project
from .release_publish_history import get_publish_history, list_publish_history, update_publish_history
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text


class RecoverRequest(BaseModel):
    action: str = "rebuild_index"


class WikiConfigSaveRequest(BaseModel):
    text: str = ""


class WikiConfigCheckRequest(BaseModel):
    text: str = ""


class WikiConfigGenerateRequest(BaseModel):
    project_id: str
    template_key: str = "single_list"


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_routes(app: FastAPI, specs: list[tuple[str, str]]) -> None:
    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def _visible_project_ids(session: Dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for project in session.get("projects", []) or []:
        identifier = str(project.get("identifier") or "").strip()
        if identifier:
            result.add(identifier)
    return result


def _require_project_access(session: Dict[str, Any], project_id: str) -> None:
    if session.get("is_admin"):
        return
    if not project_id:
        raise _json_error("普通用户查询历史时必须指定项目", 403)
    if project_id not in _visible_project_ids(session):
        raise _json_error("无权访问该项目", 403)


def _limit_history_count(limit: int) -> int:
    return max(1, min(int(limit or 50), 200))


def _list_visible_publish_history(session: Dict[str, Any], project_id: str, wiki_title: str, limit: int) -> list[dict[str, Any]]:
    if project_id:
        _require_project_access(session, project_id)
        return list_publish_history(project_id=project_id, wiki_title=wiki_title, limit=limit)
    if session.get("is_admin"):
        return list_publish_history(project_id="", wiki_title=wiki_title, limit=limit)

    limited = _limit_history_count(limit)
    items: list[dict[str, Any]] = []
    for visible_project in sorted(_visible_project_ids(session)):
        items.extend(list_publish_history(project_id=visible_project, wiki_title=wiki_title, limit=limited))
    items.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
    return items[:limited]


def _list_visible_mail_history(session: Dict[str, Any], project_id: str, wiki_title: str, limit: int) -> list[dict[str, Any]]:
    if project_id:
        _require_project_access(session, project_id)
        return list_mail_history(project_id=project_id, wiki_title=wiki_title, limit=limit)
    if session.get("is_admin"):
        return list_mail_history(project_id="", wiki_title=wiki_title, limit=limit)

    limited = _limit_history_count(limit)
    items: list[dict[str, Any]] = []
    for visible_project in sorted(_visible_project_ids(session)):
        items.extend(list_mail_history(project_id=visible_project, wiki_title=wiki_title, limit=limited))
    items.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
    return items[:limited]


def apply_security_route_overrides(app: FastAPI) -> None:
    if getattr(app.state, "security_route_overrides_registered", False):
        return
    app.state.security_route_overrides_registered = True

    _remove_routes(
        app,
        [
            ("/api/mail/history", "GET"),
            ("/api/releases/publish-history", "GET"),
            ("/api/releases/publish-history/{history_id}/recover", "POST"),
            ("/api/wiki-config/templates", "GET"),
            ("/api/wiki-config/generate", "POST"),
            ("/api/wiki-config/check", "POST"),
            ("/api/wiki-config/{project_id}/refresh-preview", "GET"),
            ("/api/wiki-config/{project_id}/refresh", "POST"),
            ("/api/wiki-config/{project_id}", "GET"),
            ("/api/wiki-config/{project_id}", "PUT"),
        ],
    )

    @app.get("/api/mail/history")
    def api_mail_history(
        project_id: str = Query(""),
        wiki_title: str = Query(""),
        limit: int = Query(50),
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "items": _list_visible_mail_history(session, project_id=project_id, wiki_title=wiki_title, limit=limit),
        }

    @app.get("/api/releases/publish-history")
    def api_publish_history(
        project_id: str = "",
        wiki_title: str = "",
        limit: int = 50,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "items": _list_visible_publish_history(session, project_id=project_id, wiki_title=wiki_title, limit=limit),
        }

    @app.post("/api/releases/publish-history/{history_id}/recover")
    def api_recover_publish_history(
        history_id: int,
        payload: RecoverRequest,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        item = get_publish_history(history_id)
        if not item:
            return JSONResponse(status_code=404, content={"detail": "发布历史不存在"})

        project_id = item.get("project_id") or ""
        _require_project_access(session, project_id)
        logs = list(item.get("logs") or [])
        action = (payload.action or "rebuild_index").strip()

        try:
            if action == "rebuild_index":
                count = IndexSync(client, project_id).refresh_all()
                logs.append(f"恢复操作：重建版本索引完成，共处理 {count} 个 Release 页面")
                update_publish_history(history_id, index_status="success", logs=logs, error_message="")
                return {"ok": True, "message": f"重建索引完成，共处理 {count} 个 Release 页面", "logs": logs}

            if action == "continue":
                form_payload = item.get("form_payload") or {}
                if form_payload.get("has_files"):
                    raise RedmineError("原发布包含本地附件，服务器无法自动恢复附件内容。请重新选择文件后重新发布。")
                changelog = str(form_payload.get("changelog") or "")
                form = ReleaseForm(
                    project_id=project_id,
                    proj_tag=proj_tag_from_project(project_id, item.get("wiki_title") or form_payload.get("edit_title") or None),
                    version_name=str(form_payload.get("version_name") or item.get("version_name") or "").strip(),
                    release_date=str(form_payload.get("release_date") or "").strip(),
                    commit=str(form_payload.get("commit") or "").strip(),
                    product_line=str(form_payload.get("product_line") or "").strip(),
                    changelog_items=[line.strip() for line in changelog.splitlines() if line.strip()],
                    files=[],
                    wiki_title=item.get("wiki_title") or form_payload.get("edit_title") or None,
                    replace_attachments=False,
                )
                title = ReleasePublisher(client).publish(form, logs)
                logs.append(f"恢复操作：继续发布完成：{title}")
                update_publish_history(
                    history_id,
                    wiki_title=title,
                    release_status="success",
                    file_status="success",
                    wiki_status="success",
                    index_status="success",
                    logs=logs,
                    error_message="",
                )
                return {"ok": True, "message": f"继续发布完成：{title}", "logs": logs}

            raise RedmineError(f"不支持的恢复操作：{action}")
        except RedmineError as exc:
            logs.append(f"恢复操作失败：{exc}")
            update_publish_history(history_id, error_message=str(exc), logs=logs)
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

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
        return {
            "ok": True,
            "updated_release_count": updated_count,
            "preview": preview,
            "message": f"已按当前 Release_Tool_Config 重建索引，处理 Release {updated_count} 个。",
        }

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
        return {"message": f"已保存到 {CONFIG_PAGE_TITLE}。{msg}"}
