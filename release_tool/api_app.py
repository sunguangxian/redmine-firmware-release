"""FastAPI 应用共享入口。

本模块只保留全局 app、公共请求模型、依赖和通用 helper。
具体业务接口由 app_factory 统一注册到独立 *_api 模块，避免旧路由和新路由同时存在。
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_external_email_settings,
    get_user_internal_email_settings,
    store_user_external_email_settings,
    store_user_internal_email_settings,
)
from .email_sender import EmailSendError, EmailSettings, send_release_email, split_emails
from .legacy_job_store import append_legacy_job_log, legacy_job_snapshot, update_legacy_job
from .mail_history import record_mail_send
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import PRODUCT_LINES, parse_inline_ref
from .session_store import InMemorySessionStore

SESSION_COOKIE = "release_tool_session"
MAIL_SCOPES = {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL}
SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_STORE = InMemorySessionStore(SESSIONS)
RECENT_RELEASE_LIMIT = 50

app = FastAPI(title="Redmine Firmware Release API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    auth_mode: str = "password"
    username: str = ""
    password: str = ""
    api_key: str = ""
    remember: bool = False


class LoginResponse(BaseModel):
    connected: bool
    user_login: str
    is_admin: bool
    projects: List[Dict[str, Any]]


class SmtpServerConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_from: str = ""
    use_tls: bool = False


class ContactConfig(BaseModel):
    contacts: List[str] = Field(default_factory=list)
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)


class ContactPersonConfig(BaseModel):
    name: str = ""
    email: str = ""


class ContactTemplateConfig(BaseModel):
    name: str = ""
    contacts_to: List[ContactPersonConfig] = Field(default_factory=list)
    contacts_cc: List[ContactPersonConfig] = Field(default_factory=list)


class AdminMailSettingsRequest(BaseModel):
    internal_server: SmtpServerConfig
    external_server: SmtpServerConfig
    internal_contacts: ContactConfig


class UserExternalMailRequest(BaseModel):
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)
    contact_templates: List[ContactTemplateConfig] = Field(default_factory=list)


class UserInternalMailRequest(BaseModel):
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)
    contact_templates: List[ContactTemplateConfig] = Field(default_factory=list)


def _user_key(base_url: str, login: str) -> str:
    return f"{base_url.rstrip('/')}|{login}"


def _json_error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _normalize_mail_scope(scope: Optional[str]) -> str:
    value = (scope or MAIL_SCOPE_INTERNAL).strip().lower()
    if value not in MAIL_SCOPES:
        raise _json_error("邮件类型只能是 internal 或 external")
    return value


def _mail_scope_label(scope: str) -> str:
    return "外网" if scope == MAIL_SCOPE_EXTERNAL else "内网"


def _current_session(request: Request) -> Dict[str, Any]:
    sid = request.cookies.get(SESSION_COOKIE, "")
    session = SESSION_STORE.get(sid)
    if not session or not session.get("connected"):
        raise _json_error("请先登录 Redmine", 401)
    return session


def _current_client(session: Dict[str, Any] = Depends(_current_session)) -> RedmineClient:
    return RedmineClient(
        session.get("base_url", ""),
        session.get("username", ""),
        session.get("password", ""),
        api_key=session.get("api_key", ""),
        auth_mode=session.get("auth_mode", "password"),
    )


def _client_from_session(session: Dict[str, Any]) -> RedmineClient:
    return RedmineClient(
        session.get("base_url", ""),
        session.get("username", ""),
        session.get("password", ""),
        api_key=session.get("api_key", ""),
        auth_mode=session.get("auth_mode", "password"),
    )


def _require_admin(session: Dict[str, Any]) -> None:
    if not session.get("is_admin"):
        raise _json_error("只有 Redmine 管理员可以修改该配置", 403)


def _public_session(session: Dict[str, Any]) -> LoginResponse:
    return LoginResponse(
        connected=True,
        user_login=session.get("user_login", ""),
        is_admin=bool(session.get("is_admin")),
        projects=session.get("projects", []),
    )


def _list_release_rows(client: RedmineClient, project_id: str, product_line: str = "") -> List[Dict[str, Any]]:
    releases = ReleasePublisher(client).list_releases(project_id)
    if product_line:
        releases = [item for item in releases if item.get("product_line") == product_line]
    return releases[:RECENT_RELEASE_LIMIT]


def _visible_projects_for_user(client: RedmineClient, projects: List[Dict[str, Any]], is_admin: bool) -> List[Dict[str, Any]]:
    if is_admin:
        return projects
    candidates = client.list_projects(membership=True)
    visible: List[Dict[str, Any]] = []
    for project in candidates:
        identifier = str(project.get("identifier") or "")
        if not identifier:
            continue
        try:
            client.get_wiki_index(identifier)
        except RedmineError:
            continue
        visible.append(project)
    return visible


def _contact_people(emails: List[str]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for email in emails:
        value = (email or "").strip()
        if not value or "@" not in value:
            continue
        result.append({"name": value.split("@")[0] or value, "email": value})
    return result


def _merge_contact_lists(*groups: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for group in groups:
        for item in group:
            email = (item or "").strip()
            key = email.lower()
            if not email or key in seen:
                continue
            seen.add(key)
            result.append(email)
    return result


def _contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    if scope == MAIL_SCOPE_INTERNAL:
        global_contacts = get_internal_contact_settings()
        user_contacts = get_user_internal_email_settings(session.get("user_key", ""))
        return {
            "contacts_to": _merge_contact_lists(global_contacts.get("contacts_to", []), user_contacts.get("contacts_to", [])),
            "contacts_cc": _merge_contact_lists(global_contacts.get("contacts_cc", []), user_contacts.get("contacts_cc", [])),
            "contact_templates": user_contacts.get("contact_templates", []),
        }

    contacts = get_user_external_email_settings(session.get("user_key", ""))
    return {
        "contacts_to": contacts.get("contacts_to", []),
        "contacts_cc": contacts.get("contacts_cc", []),
        "contact_templates": contacts.get("contact_templates", []),
    }


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
            _merge_contact_lists(global_contacts.get("contacts_to", []), user_cfg.get("contacts_to", [])),
            _merge_contact_lists(global_contacts.get("contacts_cc", []), user_cfg.get("contacts_cc", [])),
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
    if not project_id.strip():
        raise ValueError("请选择项目")
    if not version_name.strip():
        raise ValueError("请填写版本号")
    if not release_date.strip():
        raise ValueError("请选择发布日期")
    try:
        datetime.strptime(release_date.strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("发布日期格式必须是 YYYY-MM-DD") from exc
    if not commit.strip():
        raise ValueError("请填写 Commit")
    if not changelog_items:
        raise ValueError("请填写至少一条变更说明")


def _validate_notice_preflight(
    session: Dict[str, Any],
    mail_scope: str,
    mail_to: str,
    mail_cc: str,
    mail_subject: str,
    mail_body: str,
) -> Tuple[str, List[str], List[str]]:
    try:
        scope = _normalize_mail_scope(mail_scope)
    except HTTPException as exc:
        raise EmailSendError(str(exc.detail)) from exc

    settings, _allowed_to, _allowed_cc = _build_email_settings(session, scope)
    if not settings.smtp_host:
        raise EmailSendError("请先填写 SMTP 服务器")
    if not settings.smtp_from:
        raise EmailSendError("请先填写发件人邮箱")

    to_addrs = split_emails(mail_to)
    cc_addrs = split_emails(mail_cc)
    if not to_addrs:
        raise EmailSendError("请填写或选择至少一个收件人")
    if not (mail_subject or "").strip():
        raise EmailSendError("请先生成或填写邮件主题")
    if not (mail_body or "").strip():
        raise EmailSendError("请先生成或填写邮件正文")
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


@app.get("/api/meta")
def api_meta() -> Dict[str, Any]:
    return {
        "product_lines": list(PRODUCT_LINES.keys()),
        "mail_scopes": [
            {"label": "内网邮件", "value": MAIL_SCOPE_INTERNAL},
            {"label": "外网邮件", "value": MAIL_SCOPE_EXTERNAL},
        ],
        "today": date.today().isoformat(),
    }


@app.get("/api/projects")
def api_projects(session: Dict[str, Any] = Depends(_current_session), client: RedmineClient = Depends(_current_client)) -> List[Dict[str, Any]]:
    if not session.get("is_admin"):
        session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
    return session.get("projects", [])


@app.get("/api/mail/settings")
def api_mail_settings(session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
    internal_server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
    external_server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    internal_contacts = get_internal_contact_settings()
    user_internal = get_user_internal_email_settings(session.get("user_key", ""))
    user_external = get_user_external_email_settings(session.get("user_key", ""))
    return {
        "is_admin": bool(session.get("is_admin")),
        "admin": {
            "internal_server": internal_server,
            "external_server": external_server,
            "internal_contacts": internal_contacts,
        },
        "user_internal": {
            "smtp_user": user_internal["smtp_user"],
            "smtp_password": "",
            "smtp_password_set": bool(user_internal.get("smtp_password")),
            "smtp_from": user_internal["smtp_from"],
            "contacts_to": user_internal["contacts_to"],
            "contacts_cc": user_internal["contacts_cc"],
            "contact_templates": user_internal["contact_templates"],
        },
        "user_external": {
            "smtp_user": user_external["smtp_user"],
            "smtp_password": "",
            "smtp_password_set": bool(user_external.get("smtp_password")),
            "smtp_from": user_external["smtp_from"],
            "contacts_to": user_external["contacts_to"],
            "contacts_cc": user_external["contacts_cc"],
            "contact_templates": user_external["contact_templates"],
        },
    }


@app.put("/api/mail/user-internal-settings")
def api_save_user_internal_mail_settings(payload: UserInternalMailRequest, session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, bool]:
    user_key = session.get("user_key", "")
    old = get_user_internal_email_settings(user_key)
    smtp_password = payload.smtp_password or old.get("smtp_password", "")
    store_user_internal_email_settings(
        user_key,
        smtp_user=payload.smtp_user,
        smtp_password=smtp_password,
        smtp_from=payload.smtp_from,
        contacts_to=payload.contacts_to,
        contacts_cc=payload.contacts_cc,
        contact_templates=[item.dict() for item in payload.contact_templates],
    )
    return {"ok": True}


@app.put("/api/mail/user-external-settings")
def api_save_user_external_mail_settings(payload: UserExternalMailRequest, session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, bool]:
    user_key = session.get("user_key", "")
    old = get_user_external_email_settings(user_key)
    smtp_password = payload.smtp_password or old.get("smtp_password", "")
    store_user_external_email_settings(
        user_key,
        smtp_user=payload.smtp_user,
        smtp_password=smtp_password,
        smtp_from=payload.smtp_from,
        contacts_to=payload.contacts_to,
        contacts_cc=payload.contacts_cc,
        contact_templates=[item.dict() for item in payload.contact_templates],
    )
    return {"ok": True}


@app.get("/api/mail/contacts")
def api_mail_contacts(scope: str = Query(MAIL_SCOPE_INTERNAL), session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
    return _contacts_for_scope(session, _normalize_mail_scope(scope))


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
    uvicorn.run("release_tool.api_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
