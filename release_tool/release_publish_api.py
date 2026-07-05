"""正式发布接口。

替换 api_app 中早期的 /api/releases/publish 实现，直接返回 Redmine 和邮件拆分状态，
并记录发布执行历史。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .access_control import list_visible_history, require_project_access
from .api_app import (
    MAIL_SCOPE_INTERNAL,
    _current_client,
    _current_session,
    _list_release_rows,
    _mail_scope_label,
    _send_release_notice,
    _validate_notice_preflight,
    _validate_release_preflight,
)
from .email_sender import EmailSendError
from .index_sync import IndexSync
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, proj_tag_from_project
from .release_publish_history import create_publish_history, get_publish_history, list_publish_history, update_publish_history


class RecoverRequest(BaseModel):
    action: str = "rebuild_index"


def _remove_existing_publish_route(app: FastAPI) -> None:
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", "") == "/api/releases/publish" and "POST" in getattr(route, "methods", set()))
    ]


def _mail_status_label(status: str) -> str:
    if status == "success":
        return "成功"
    if status == "failed":
        return "失败，可重试"
    return "未启用"


async def _read_upload_files(files: Optional[List[UploadFile]]) -> List[Tuple[str, str, bytes]]:
    rows: List[Tuple[str, str, bytes]] = []
    for upload in files or []:
        content = await upload.read()
        if upload.filename and content:
            rows.append((upload.filename, "", content))
    return rows


def _form_payload(
    *,
    project_id: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog: str,
    replace_attachments: bool,
    edit_title: str,
    has_files: bool,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "version_name": version_name,
        "release_date": release_date,
        "commit": commit,
        "product_line": product_line,
        "changelog": changelog,
        "replace_attachments": bool(replace_attachments),
        "edit_title": edit_title,
        "has_files": bool(has_files),
    }


def register_release_publish_routes(app: FastAPI) -> None:
    if getattr(app.state, "release_publish_routes_registered", False):
        return
    app.state.release_publish_routes_registered = True
    _remove_existing_publish_route(app)

    @app.post("/api/releases/publish")
    async def api_publish_release(
        project_id: str = Form(...),
        version_name: str = Form(...),
        release_date: str = Form(...),
        commit: str = Form(...),
        product_line: str = Form(""),
        changelog: str = Form(...),
        replace_attachments: bool = Form(False),
        edit_title: str = Form(""),
        notice_enabled: bool = Form(False),
        mail_scope: str = Form(MAIL_SCOPE_INTERNAL),
        mail_to: str = Form(""),
        mail_cc: str = Form(""),
        mail_subject: str = Form(""),
        mail_body: str = Form(""),
        files: Optional[List[UploadFile]] = File(None),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        require_project_access(session, project_id)
        logs: List[str] = []
        action = "编辑版本" if edit_title else "发布新版本"
        items = [line.strip() for line in changelog.splitlines() if line.strip()]
        file_rows = await _read_upload_files(files)
        payload = _form_payload(
            project_id=project_id,
            version_name=version_name,
            release_date=release_date,
            commit=commit,
            product_line=product_line,
            changelog=changelog,
            replace_attachments=replace_attachments,
            edit_title=edit_title,
            has_files=bool(file_rows),
        )
        history_id = create_publish_history(project_id=project_id, version_name=version_name, action=action, logs=logs, form_payload=payload)
        notice_scope = ""
        notice_to_addrs: List[str] = []
        notice_cc_addrs: List[str] = []
        title = edit_title or ""
        mail_status = "skipped"
        notice_message = ""

        try:
            logs.append(f"开始{action}：项目 {project_id}")
            _validate_release_preflight(project_id, version_name, release_date, commit, items)
            logs.append("基础字段预检查通过")
            logs.append(f"变更说明校验通过：{len(items)} 条")
            if notice_enabled:
                notice_scope, notice_to_addrs, notice_cc_addrs = _validate_notice_preflight(session, mail_scope, mail_to, mail_cc, mail_subject, mail_body)
                logs.append(f"邮件预检查通过：{_mail_scope_label(notice_scope)}，收件人 {len(notice_to_addrs)} 个，抄送 {len(notice_cc_addrs)} 个")
            else:
                logs.append("邮件通知未启用，跳过邮件预检查")
        except (ValueError, EmailSendError) as exc:
            logs.append(f"预检查失败：{exc}")
            update_publish_history(history_id, release_status="failed", file_status="failed", wiki_status="failed", index_status="failed", mail_status="skipped", error_message=str(exc), logs=logs)
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

        logs.append(f"附件读取完成：{len(file_rows)} 个有效附件")
        form = ReleaseForm(
            project_id=project_id,
            proj_tag=proj_tag_from_project(project_id, edit_title or None),
            version_name=version_name.strip(),
            release_date=release_date.strip(),
            commit=commit.strip(),
            product_line=product_line.strip(),
            changelog_items=items,
            files=file_rows,
            wiki_title=edit_title or None,
            replace_attachments=bool(replace_attachments),
        )

        try:
            title = ReleasePublisher(client).publish(form, logs)
            update_publish_history(history_id, wiki_title=title, release_status="success", file_status="success", wiki_status="success", index_status="success", logs=logs)
        except RedmineError as exc:
            logs.append(f"{action}失败：{exc}")
            update_publish_history(history_id, wiki_title=title, release_status="failed", file_status="unknown", wiki_status="unknown", index_status="unknown", mail_status="skipped", error_message=str(exc), logs=logs)
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

        if notice_enabled:
            try:
                logs.append(f"邮件通知已启用：{_mail_scope_label(notice_scope)}，收件人 {len(notice_to_addrs)} 个，抄送 {len(notice_cc_addrs)} 个")
                notice_message = _send_release_notice(session=session, client=client, project_id=project_id, wiki_title=title, version_name=version_name.strip(), file_rows=file_rows, mail_scope=notice_scope, mail_to=notice_to_addrs, mail_cc=notice_cc_addrs, mail_subject=mail_subject, mail_body=mail_body)
                mail_status = "success"
                notice_message = f"邮件发送：成功，{notice_message}"
                logs.append(notice_message)
            except EmailSendError as exc:
                mail_status = "failed"
                notice_message = f"邮件发送失败：{exc}"
                logs.append(notice_message)
        else:
            logs.append("邮件通知未启用，跳过发送")

        releases = _list_release_rows(client, project_id, product_line.strip())
        logs.append(f"刷新版本列表完成：返回 {len(releases)} 条")
        logs.append(f"{action}完成：{title}")
        update_publish_history(history_id, wiki_title=title, form_payload={**payload, "edit_title": title}, mail_status=mail_status, logs=logs)
        return {"ok": True, "title": title, "notice_message": notice_message, "releases": releases, "logs": logs, "publish_history_id": history_id, "release_status": "success", "release_status_label": "Redmine 发布成功", "file_status": "success", "wiki_status": "success", "index_status": "success", "mail_status": mail_status, "mail_status_label": f"邮件发送{_mail_status_label(mail_status)}", "result_summary": f"Redmine 发布：成功\n邮件发送：{_mail_status_label(mail_status)}"}

    @app.get("/api/releases/publish-history")
    def api_publish_history(
        project_id: str = "",
        wiki_title: str = "",
        limit: int = 50,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "items": list_visible_history(
                session,
                project_id=project_id,
                wiki_title=wiki_title,
                limit=limit,
                loader=list_publish_history,
            ),
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
        require_project_access(session, project_id)
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
                update_publish_history(history_id, wiki_title=title, release_status="success", file_status="success", wiki_status="success", index_status="success", logs=logs, error_message="")
                return {"ok": True, "message": f"继续发布完成：{title}", "logs": logs}
            raise RedmineError(f"不支持的恢复操作：{action}")
        except RedmineError as exc:
            logs.append(f"恢复操作失败：{exc}")
            update_publish_history(history_id, error_message=str(exc), logs=logs)
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})
