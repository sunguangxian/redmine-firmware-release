"""内联模式兼容的发布预览接口。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .api_app import _current_client, _current_session, _mail_scope_label, _validate_notice_preflight, _validate_release_preflight
from .email_sender import EmailSendError
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_ops_api import _build_preview_lines, _read_preview_files, _split_changelog
from .release_page import ReleaseForm, extract_inline_release_block, inline_ref, parse_inline_ref, parse_release_files, parse_release_page, proj_tag_from_project
from .release_structure_guard import ensure_release_structure_ready


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_preview_route(app: FastAPI) -> None:
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", "") == "/api/releases/preview" and _route_has_method(route, "POST"))
    ]


def _is_inline_profile(profile: Any) -> bool:
    return getattr(profile, "release_detail_mode", "inline") == "inline"


def _inline_display_version(block_id: str, block: str) -> str:
    if not block:
        return ""
    try:
        parsed = parse_release_page(inline_ref("_", block_id), block)
        return str(parsed.get("version_name") or "").strip()
    except Exception:
        return ""


def _inline_preview_target(index_sync: Any, profile: Any, form: ReleaseForm, edit_title: str) -> tuple[str, str, str, str, int]:
    inline_target = parse_inline_ref(edit_title)
    if inline_target:
        container_page, old_block_id = inline_target
        page = index_sync.client.get_wiki_page(form.project_id, container_page)
        block = extract_inline_release_block((page or {}).get("text", ""), old_block_id)
        old_display_version = _inline_display_version(old_block_id, block)
        return f"{container_page} / {form.version_name}", container_page, old_block_id, old_display_version, len(parse_release_files(block)) if block else 0

    container_page = index_sync.inline_container_for_release(
        profile,
        form.page_title,
        f"**产品线:** {form.product_line}\n**Commit:** {form.commit}\n",
    )
    block_id = form.version_name.strip()
    return f"{container_page} / {form.version_name}", container_page, block_id, block_id, 0


def register_release_preview_routes(app: FastAPI) -> None:
    if getattr(app.state, "release_preview_routes_registered", False):
        return
    app.state.release_preview_routes_registered = True
    _remove_existing_preview_route(app)

    @app.post("/api/releases/preview")
    async def api_preview_release(
        project_id: str = Form(...),
        version_name: str = Form(...),
        release_date: str = Form(...),
        commit: str = Form(...),
        product_line: str = Form(""),
        changelog: str = Form(...),
        replace_attachments: bool = Form(False),
        edit_title: str = Form(""),
        notice_enabled: bool = Form(False),
        mail_scope: str = Form("internal"),
        mail_to: str = Form(""),
        mail_cc: str = Form(""),
        mail_subject: str = Form(""),
        mail_body: str = Form(""),
        files: Optional[List[UploadFile]] = File(None),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        logs: List[str] = []
        action = "编辑版本" if edit_title else "发布新版本"
        items = _split_changelog(changelog)
        warnings: List[str] = []
        try:
            _validate_release_preflight(project_id, version_name, release_date, commit, items)
            logs.append("基础字段预检查通过")
            index_sync, profile = ensure_release_structure_ready(client, project_id, logs)

            if notice_enabled:
                notice_scope, notice_to_addrs, notice_cc_addrs = _validate_notice_preflight(session, mail_scope, mail_to, mail_cc, mail_subject, mail_body)
                mail_scope_label = _mail_scope_label(notice_scope)
            else:
                notice_to_addrs = []
                notice_cc_addrs = []
                mail_scope_label = ""

            preview_files = await _read_preview_files(files)
            form = ReleaseForm(
                project_id=project_id,
                proj_tag=proj_tag_from_project(project_id, edit_title or None),
                version_name=version_name.strip(),
                release_date=release_date.strip(),
                commit=commit.strip(),
                product_line=product_line.strip(),
                changelog_items=items,
                files=[(item["filename"], "", b"x") for item in preview_files],
                wiki_title=edit_title or None,
                replace_attachments=bool(replace_attachments),
            )

            publisher = ReleasePublisher(client)
            publisher._validate_category(form, index_sync, profile, logs)
            version_plan = "将复用已有 Version"
            version_name_final = publisher._configured_version_name(form, index_sync, profile)
            if not any(v.get("name", "").strip() == version_name_final for v in client.list_versions(project_id)):
                version_plan = "将创建新 Version"

            old_files_count = 0
            if _is_inline_profile(profile):
                wiki_title, _container_page, old_block_id, old_display_version, old_files_count = _inline_preview_target(index_sync, profile, form, edit_title)
                if edit_title and old_block_id == (old_display_version or old_block_id) and old_block_id != form.version_name.strip():
                    warnings.append(f"本次会把旧内联版本块 {old_block_id} 重命名为 {form.version_name.strip()}。")
                elif edit_title and old_block_id != form.version_name.strip():
                    warnings.append(f"本次会保留唯一块标识 {old_block_id}，页面显示版本更新为 {form.version_name.strip()}。")
            else:
                generated_title = publisher._configured_release_title(form, index_sync, profile)
                wiki_title = edit_title or generated_title or form.page_title
                if edit_title:
                    page = client.get_wiki_page(project_id, edit_title)
                    if page:
                        old_files_count = len(parse_release_files(page.get("text", "")))

            if edit_title:
                if replace_attachments and not preview_files:
                    warnings.append("编辑版本未选择新附件，实际更新时会自动保留已有附件列表。")
                    attachment_plan = f"保留已有附件 {old_files_count} 个，不上传新附件"
                elif replace_attachments:
                    attachment_plan = f"用 {len(preview_files)} 个新附件替换旧附件列表"
                else:
                    attachment_plan = f"保留已有附件 {old_files_count} 个，并追加 {len(preview_files)} 个新附件"
            else:
                attachment_plan = f"上传 {len(preview_files)} 个新附件"
                if not preview_files:
                    warnings.append("本次发布没有选择附件，Wiki 文件列表会显示为空。")

            preview = {
                "ok": True,
                "action": action,
                "project_id": project_id,
                "version_name": version_name.strip(),
                "release_date": release_date.strip(),
                "wiki_title": wiki_title,
                "version_plan": version_plan,
                "attachment_plan": attachment_plan,
                "files": preview_files,
                "notice_enabled": bool(notice_enabled),
                "mail_scope_label": mail_scope_label,
                "mail_to_count": len(notice_to_addrs),
                "mail_cc_count": len(notice_cc_addrs),
                "warnings": warnings,
                "logs": logs,
            }
            return {**preview, "summary": "\n".join(_build_preview_lines(preview))}
        except (ValueError, EmailSendError, RedmineError) as exc:
            logs.append(f"预览失败：{exc}")
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})
