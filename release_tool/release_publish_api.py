"""正式发布接口。

替换 api_app 中早期的 /api/releases/publish 实现，直接返回 Redmine 和邮件拆分状态，
并记录发布执行历史。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

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
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, proj_tag_from_project
from .release_publish_history import create_publish_history, list_publish_history, update_publish_history


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
        logs: List[str] = []
        action = "编辑版本" if edit_title else "发布新版本"
        items = [line.strip() for line in changelog.splitlines() if line.strip()]
        history_id = create_publish_history(project_id=project_id, version_name=version_name, action=action, logs=logs)
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
                notice_scope, notice_to_addrs, notice_cc_addrs = _validate_notice_preflight(
                    session,
                    mail_scope,
                    mail_to,
                    mail_cc,
                    mail_subject,
                    mail_body,
                )
                logs.append(
                    f"邮件预检查通过：{_mail_scope_label(notice_scope)}，"
                    f"收件人 {len(notice_to_addrs)} 个，抄送 {len(notice_cc_addrs)} 个"
                )
            else:
                logs.append("邮件通知未启用，跳过邮件预检查")
        except (ValueError, EmailSendError) as exc:
            logs.append(f"预检查失败：{exc}")
            update_publish_history(
                history_id,
                release_status="failed",
                file_status="failed",
                wiki_status="failed",
                index_status="failed",
                mail_status="skipped",
                error_message=str(exc),
                logs=logs,
            )
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

        file_rows = await _read_upload_files(files)
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
            update_publish_history(
                history_id,
                wiki_title=title,
                release_status="success",
                file_status="success",
                wiki_status="success",
                index_status="success",
                logs=logs,
            )
        except RedmineError as exc:
            logs.append(f"{action}失败：{exc}")
            update_publish_history(
                history_id,
                wiki_title=title,
                release_status="failed",
                file_status="unknown",
                wiki_status="unknown",
                index_status="unknown",
                mail_status="skipped",
                error_message=str(exc),
                logs=logs,
            )
            return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

        if notice_enabled:
            try:
                logs.append(f"邮件通知已启用：{_mail_scope_label(notice_scope)}，收件人 {len(notice_to_addrs)} 个，抄送 {len(notice_cc_addrs)} 个")
                notice_message = _send_release_notice(
                    session=session,
                    client=client,
                    project_id=project_id,
                    wiki_title=title,
                    version_name=version_name.strip(),
                    file_rows=file_rows,
                    mail_scope=notice_scope,
                    mail_to=notice_to_addrs,
                    mail_cc=notice_cc_addrs,
                    mail_subject=mail_subject,
                    mail_body=mail_body,
                )
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
        update_publish_history(history_id, mail_status=mail_status, logs=logs)
        return {
            "ok": True,
            "title": title,
            "notice_message": notice_message,
            "releases": releases,
            "logs": logs,
            "publish_history_id": history_id,
            "release_status": "success",
            "release_status_label": "Redmine 发布成功",
            "file_status": "success",
            "wiki_status": "success",
            "index_status": "success",
            "mail_status": mail_status,
            "mail_status_label": f"邮件发送{_mail_status_label(mail_status)}",
            "result_summary": f"Redmine 发布：成功\n邮件发送：{_mail_status_label(mail_status)}",
        }

    @app.get("/api/releases/publish-history")
    def api_publish_history(
        project_id: str = "",
        wiki_title: str = "",
        limit: int = 50,
        _session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "items": list_publish_history(project_id=project_id, wiki_title=wiki_title, limit=limit),
        }
