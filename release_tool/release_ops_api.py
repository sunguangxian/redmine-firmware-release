"""发布预览和邮件重发接口。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .api_app import (
    _current_client,
    _current_session,
    _mail_scope_label,
    _send_release_notice,
    _validate_notice_preflight,
    _validate_release_preflight,
)
from .email_sender import EmailSendError
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, parse_release_files, proj_tag_from_project
from .release_structure_guard import ensure_release_structure_ready


def _split_changelog(changelog: str) -> List[str]:
    return [line.strip() for line in (changelog or "").splitlines() if line.strip()]


async def _read_preview_files(files: Optional[List[UploadFile]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for upload in files or []:
        content = await upload.read()
        if upload.filename and content:
            result.append({"filename": upload.filename, "size": len(content)})
    return result


async def _read_mail_files(files: Optional[List[UploadFile]]) -> List[Tuple[str, str, bytes]]:
    result: List[Tuple[str, str, bytes]] = []
    for upload in files or []:
        content = await upload.read()
        if upload.filename and content:
            result.append((upload.filename, "", content))
    return result


def _size_text(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _build_preview_lines(preview: Dict[str, Any]) -> List[str]:
    lines = [
        f"操作：{preview['action']}",
        f"项目：{preview['project_id']}",
        f"版本：{preview['version_name']}",
        f"日期：{preview['release_date']}",
        f"Wiki 页面：{preview['wiki_title']}",
        f"Redmine Version：{preview['version_plan']}",
        f"附件策略：{preview['attachment_plan']}",
    ]
    if preview["files"]:
        lines.append("新附件：")
        lines.extend(f"- {item['filename']} ({_size_text(item['size'])})" for item in preview["files"])
    else:
        lines.append("新附件：无")
    if preview["notice_enabled"]:
        lines.append(
            f"邮件：{preview['mail_scope_label']}，收件人 {preview['mail_to_count']} 个，抄送 {preview['mail_cc_count']} 个"
        )
    else:
        lines.append("邮件：不发送")
    if preview["warnings"]:
        lines.append("注意：")
        lines.extend(f"- {item}" for item in preview["warnings"])
    return lines


def register_release_ops_routes(app: FastAPI) -> None:
    if getattr(app.state, "release_ops_routes_registered", False):
        return
    app.state.release_ops_routes_registered = True

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
                notice_scope, notice_to_addrs, notice_cc_addrs = _validate_notice_preflight(
                    session, mail_scope, mail_to, mail_cc, mail_subject, mail_body
                )
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
            generated_title = publisher._configured_release_title(form, index_sync, profile)
            wiki_title = edit_title or generated_title or form.page_title
            version_plan = "将复用已有 Version"
            version_name_final = publisher._configured_version_name(form, index_sync, profile)
            if not any(v.get("name", "").strip() == version_name_final for v in client.list_versions(project_id)):
                version_plan = "将创建新 Version"

            old_files_count = 0
            if edit_title:
                page = client.get_wiki_page(project_id, edit_title)
                if page:
                    old_files_count = len(parse_release_files(page.get("text", "")))
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

    @app.post("/api/releases/notice/send")
    async def api_send_release_notice(
        project_id: str = Form(...),
        wiki_title: str = Form(...),
        version_name: str = Form(""),
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
        try:
            scope, to_addrs, cc_addrs = _validate_notice_preflight(
                session, mail_scope, mail_to, mail_cc, mail_subject, mail_body
            )
            file_rows = await _read_mail_files(files)
            logs.append(
                f"邮件重发预检查通过：{_mail_scope_label(scope)}，收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个"
            )
            message = _send_release_notice(
                session=session,
                client=client,
                project_id=project_id,
                wiki_title=wiki_title,
                version_name=version_name.strip(),
                file_rows=file_rows,
                mail_scope=scope,
                mail_to=to_addrs,
                mail_cc=cc_addrs,
                mail_subject=mail_subject,
                mail_body=mail_body,
            )
            logs.append(message)
            return {"ok": True, "message": message, "logs": logs}
        except EmailSendError as exc:
            logs.append(f"邮件重发失败：{exc}")
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})
