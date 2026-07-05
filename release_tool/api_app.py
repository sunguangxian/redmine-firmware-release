"""FastAPI 应用共享入口。

本模块只保留全局 app、公共导出、邮件发送 helper 和前端挂载。
具体业务接口由 app_factory 统一注册到独立 *_api 模块。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_external_email_settings,
    get_user_internal_email_settings,
)
from .dependencies import (
    SESSION_COOKIE,
    SESSION_STORE,
    SESSIONS,
    _client_from_session,
    _current_client,
    _current_session,
    _json_error,
    _public_session,
    _require_admin,
    _user_key,
    _visible_projects_for_user,
)
from .email_sender import EmailSendError, EmailSettings, send_release_email, split_emails
from .legacy_job_store import append_legacy_job_log, legacy_job_snapshot, update_legacy_job
from .mail_contact_helpers import (
    MAIL_SCOPES,
    contact_people,
    contacts_for_scope,
    mail_scope_label,
    merge_contact_lists,
    normalize_mail_scope,
)
from .mail_history import record_mail_send
from .mail_notice_helpers import validate_notice_fields
from .redmine_api import RedmineClient, RedmineError
from .release_helpers import RECENT_RELEASE_LIMIT, list_release_rows, validate_release_preflight
from .release_page import parse_inline_ref
from .schemas import (
    AdminMailSettingsRequest,
    ContactConfig,
    ContactPersonConfig,
    ContactTemplateConfig,
    LoginRequest,
    LoginResponse,
    SmtpServerConfig,
    UserExternalMailRequest,
    UserInternalMailRequest,
)

app = FastAPI(title="Redmine Firmware Release API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _list_release_rows(client: RedmineClient, project_id: str, product_line: str = "") -> List[Dict[str, Any]]:
    return list_release_rows(client, project_id, product_line)


def _contact_people(emails: List[str]) -> List[Dict[str, str]]:
    return contact_people(emails)


def _merge_contact_lists(*groups: List[str]) -> List[str]:
    return merge_contact_lists(*groups)


def _contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    return contacts_for_scope(session, scope)


def _append_legacy_job_log(job_id: str, message: str) -> None:
    append_legacy_job_log(job_id, message)


def _legacy_job_snapshot(job_id: str) -> Dict[str, Any]:
    snapshot = legacy_job_snapshot(job_id)
    if not snapshot:
        raise _json_error("旧项目升级任务不存在或已过期", 404)
    return snapshot


def _set_legacy_job_state(job_id: str, **fields: Any) -> None:
    update_legacy_job(
        job_id,
        status=fields.get("status"),
        result=fields.get("result") if "result" in fields else None,
        error=fields.get("error") if "error" in fields else None,
    )


def _normalize_mail_scope(scope: Optional[str]) -> str:
    return normalize_mail_scope(scope)


def _mail_scope_label(scope: str) -> str:
    return mail_scope_label(scope)


def _build_email_settings(session: Dict[str, Any], scope: str) -> Tuple[EmailSettings, List[str], List[str]]:
    if scope == MAIL_SCOPE_INTERNAL:
        server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        user_cfg = get_user_internal_email_settings(session.get("user_key", ""))
        if not user_cfg["smtp_user"] or not user_cfg["smtp_password"]:
            raise EmailSendError("内网邮件请先配置个人 SMTP 用户名和密码")
        if not user_cfg["smtp_from"] and not server["smtp_from"]:
            raise EmailSendError("内网邮件请先配置个人发件人或管理员默认发件人")
        global_contacts = get_internal_contact_settings()
        return (
            EmailSettings(
                smtp_host=server["smtp_host"],
                smtp_port=server["smtp_port"],
                smtp_user=user_cfg["smtp_user"],
                smtp_password=user_cfg["smtp_password"],
                smtp_from=user_cfg["smtp_from"] or server["smtp_from"],
                use_tls=server["use_tls"],
            ),
            merge_contact_lists(global_contacts.get("contacts_to", []), user_cfg.get("contacts_to", [])),
            merge_contact_lists(global_contacts.get("contacts_cc", []), user_cfg.get("contacts_cc", [])),
        )

    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    user_cfg = get_user_external_email_settings(session.get("user_key", ""))
    if not user_cfg["smtp_user"] or not user_cfg["smtp_password"]:
        raise EmailSendError("外网邮件请先配置个人 SMTP 用户名和密码")
    return (
        EmailSettings(
            smtp_host=server["smtp_host"],
            smtp_port=server["smtp_port"],
            smtp_user=user_cfg["smtp_user"],
            smtp_password=user_cfg["smtp_password"],
            smtp_from=user_cfg["smtp_from"],
            use_tls=server["use_tls"],
        ),
        user_cfg["contacts_to"],
        user_cfg["contacts_cc"],
    )


def _validate_release_preflight(
    project_id: str,
    version_name: str,
    release_date: str,
    commit: str,
    changelog_items: List[str],
) -> None:
    validate_release_preflight(project_id, version_name, release_date, commit, changelog_items)


def _validate_notice_preflight(
    session: Dict[str, Any],
    mail_scope: str,
    mail_to: str,
    mail_cc: str,
    mail_subject: str,
    mail_body: str,
) -> Tuple[str, List[str], List[str]]:
    scope, to_addrs, cc_addrs = validate_notice_fields(mail_scope, mail_to, mail_cc, mail_subject, mail_body)
    settings, _allowed_to, _allowed_cc = _build_email_settings(session, scope)
    if not settings.smtp_host:
        raise EmailSendError("请先填写 SMTP 服务器")
    if not settings.smtp_from:
        raise EmailSendError("请先填写发件人邮箱")
    return scope, to_addrs, cc_addrs


def _send_release_notice(
    *,
    session: Dict[str, Any],
    client: RedmineClient,
    project_id: str,
    wiki_title: str,
    version_name: str = "",
    file_rows: List[Tuple[str, str, bytes]],
    mail_scope: str,
    mail_to: List[str],
    mail_cc: List[str],
    mail_subject: str = "",
    mail_body: str = "",
    send_type: str = "publish",
) -> str:
    inline = parse_inline_ref(wiki_title)
    normalized_wiki_title = inline[0] if inline else wiki_title
    settings, _allowed_to, _allowed_cc = _build_email_settings(session, mail_scope)
    to_addrs = split_emails(mail_to)
    cc_addrs = split_emails(mail_cc)
    subject = (mail_subject or "").strip()
    body = (mail_body or "").strip()
    if not subject or not body:
        raise EmailSendError("请先生成或填写邮件主题和正文")
    base = client.base_url.rstrip("/")
    body = body.replace("{{wiki_url}}", f"{base}/projects/{quote(project_id)}/wiki/{quote(normalized_wiki_title, safe='')}")
    body = body.replace("{{files_url}}", f"{base}/projects/{quote(project_id)}/files")
    try:
        send_release_email(
            settings,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=subject,
            body=body,
            attachments=file_rows,
        )
        record_mail_send(
            project_id=project_id,
            wiki_title=normalized_wiki_title,
            version_name=version_name,
            scope=mail_scope,
            subject=subject,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            attachment_count=len(file_rows),
            sender_user=session.get("user_login", ""),
            status="success",
            send_type=send_type,
        )
    except EmailSendError as exc:
        record_mail_send(
            project_id=project_id,
            wiki_title=normalized_wiki_title,
            version_name=version_name,
            scope=mail_scope,
            subject=subject,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            attachment_count=len(file_rows),
            sender_user=session.get("user_login", ""),
            status="failed",
            error_message=str(exc),
            send_type=send_type,
        )
        raise
    return f"{_mail_scope_label(mail_scope)}邮件已发送：收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个，附件 {len(file_rows)} 个"


@app.exception_handler(RedmineError)
async def redmine_error_handler(_request: Request, exc: RedmineError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _mount_frontend() -> None:
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    index_file = dist / "index.html"
    if not index_file.exists():

        @app.get("/")
        def frontend_missing() -> Dict[str, str]:
            return {"message": "Vue 前端尚未构建。开发时请运行：cd frontend && npm run dev；发布时请先运行 npm run build。"}

        return

    @app.get("/")
    def frontend_index() -> FileResponse:
        return FileResponse(index_file)

    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


_mount_frontend()


def main() -> None:
    import uvicorn

    host = os.environ.get("RELEASE_TOOL_HOST", "127.0.0.1")
    port = int(os.environ.get("RELEASE_TOOL_PORT", "7860"))
    uvicorn.run("release_tool.app_factory:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
