"""FastAPI 后端入口，供 Vue 前端调用。"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    default_base_url,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_external_email_settings,
    get_user_internal_email_settings,
    store_email_server_settings,
    store_internal_contact_settings,
    store_login,
    store_user_external_email_settings,
    store_user_internal_email_settings,
)
from .email_sender import (
    EmailSendError,
    EmailSettings,
    build_release_email_body,
    build_release_email_subject,
    send_release_email,
    split_emails,
)
from .index_sync import IndexSync
from .legacy_changelog_migrator import LegacyChangelogMigrator
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import PRODUCT_LINES, ReleaseForm, format_release_files, parse_release_page, proj_tag_from_project
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text

SESSION_COOKIE = "release_tool_session"
MAIL_SCOPES = {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL}
SESSIONS: Dict[str, Dict[str, Any]] = {}
LEGACY_MIGRATION_JOBS: Dict[str, Dict[str, Any]] = {}
LEGACY_JOB_LOCK = threading.Lock()
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


class WikiConfigSaveRequest(BaseModel):
    text: str = ""


class WikiConfigCheckRequest(BaseModel):
    text: str = ""


class WikiConfigGenerateRequest(BaseModel):
    project_id: str
    template_key: str = "single_list"


class LegacyMigrationRequest(BaseModel):
    project_id: str
    entry_pages: List[str] = Field(default_factory=lambda: ["Changelog"])


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
    session = SESSIONS.get(sid)
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


def _contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    if scope == MAIL_SCOPE_INTERNAL:
        global_contacts = get_internal_contact_settings()
        user_contacts = get_user_internal_email_settings(session.get("user_key", ""))
        contact_candidates = _merge_contact_lists(
            global_contacts.get("contacts", []),
            user_contacts.get("contacts_to", []),
            user_contacts.get("contacts_cc", []),
        )
        templates = []
        templates.extend(user_contacts.get("contact_templates", []))
        return {
            "contacts_to": contact_candidates,
            "contacts_cc": contact_candidates,
            "contact_templates": templates,
        }
    else:
        contacts = get_user_external_email_settings(session.get("user_key", ""))
    return {
        "contacts_to": contacts.get("contacts_to", []),
        "contacts_cc": contacts.get("contacts_cc", []),
        "contact_templates": contacts.get("contact_templates", []),
    }


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


def _job_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _append_legacy_job_log(job_id: str, message: str) -> None:
    with LEGACY_JOB_LOCK:
        job = LEGACY_MIGRATION_JOBS.get(job_id)
        if job is not None:
            job.setdefault("logs", []).append(f"{_job_timestamp()} {message}")


def _legacy_job_snapshot(job_id: str) -> Dict[str, Any]:
    with LEGACY_JOB_LOCK:
        job = LEGACY_MIGRATION_JOBS.get(job_id)
        if not job:
            raise _json_error("旧项目升级任务不存在或已过期", 404)
        return {
            "job_id": job_id,
            "status": job.get("status", "running"),
            "logs": list(job.get("logs", [])),
            "result": job.get("result"),
            "error": job.get("error", ""),
        }


def _set_legacy_job_state(job_id: str, **fields: Any) -> None:
    with LEGACY_JOB_LOCK:
        job = LEGACY_MIGRATION_JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def _run_legacy_migration_job(job_id: str, payload: LegacyMigrationRequest, session: Dict[str, Any]) -> None:
    try:
        _append_legacy_job_log(job_id, "后台任务已启动")
        client = _client_from_session(session)
        result = LegacyChangelogMigrator(
            client,
            payload.project_id,
            payload.entry_pages,
            log_callback=lambda message: _append_legacy_job_log(job_id, message),
        ).execute()
        _append_legacy_job_log(job_id, result.get("message", "旧项目升级完成"))
        _set_legacy_job_state(job_id, status="succeeded", result=result)
    except Exception as exc:
        _append_legacy_job_log(job_id, f"执行失败：{exc}")
        _set_legacy_job_state(job_id, status="failed", error=str(exc))


def _build_email_settings(session: Dict[str, Any], scope: str) -> Tuple[EmailSettings, List[str], List[str]]:
    if scope == MAIL_SCOPE_INTERNAL:
        server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        user_cfg = get_user_internal_email_settings(session.get("user_key", ""))
        if not user_cfg["smtp_user"] or not user_cfg["smtp_password"]:
            raise EmailSendError("内网邮件请先配置个人 SMTP 用户名和密码")
        if not user_cfg["smtp_from"] and not server["smtp_from"]:
            raise EmailSendError("内网邮件请先配置个人发件人或管理员默认发件人")
        global_contacts = get_internal_contact_settings()
        contact_candidates = _merge_contact_lists(
            global_contacts["contacts"],
            user_cfg["contacts_to"],
            user_cfg["contacts_cc"],
        )
        return (
            EmailSettings(
                smtp_host=server["smtp_host"],
                smtp_port=server["smtp_port"],
                smtp_user=user_cfg["smtp_user"],
                smtp_password=user_cfg["smtp_password"],
                smtp_from=user_cfg["smtp_from"] or server["smtp_from"],
                use_tls=server["use_tls"],
                template_scope=MAIL_SCOPE_INTERNAL,
            ),
            contact_candidates,
            contact_candidates,
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
            template_scope=MAIL_SCOPE_EXTERNAL,
        ),
        user_cfg["contacts_to"],
        user_cfg["contacts_cc"],
    )


def _send_release_notice(
    *,
    session: Dict[str, Any],
    client: RedmineClient,
    project_id: str,
    wiki_title: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog_items: List[str],
    file_rows: List[Tuple[str, str, bytes]],
    mail_scope: str,
    mail_to: List[str],
    mail_cc: List[str],
    mail_subject: str = "",
    mail_body: str = "",
) -> str:
    settings, _allowed_to, _allowed_cc = _build_email_settings(session, mail_scope)
    to_addrs = split_emails(mail_to)
    cc_addrs = split_emails(mail_cc)
    generated_subject = build_release_email_subject(project_id, version_name, product_line, mail_scope)
    generated_body = build_release_email_body(
        base_url=client.base_url,
        project_id=project_id,
        wiki_title=wiki_title,
        version_name=version_name,
        release_date=release_date,
        commit=commit,
        product_line=product_line,
        changelog_items=changelog_items,
        attachment_names=[name for name, _desc, _content in file_rows],
        mail_scope=mail_scope,
    )
    subject = (mail_subject or "").strip() or generated_subject
    body = (mail_body or "").strip() or generated_body
    base = client.base_url.rstrip("/")
    body = body.replace("{{wiki_url}}", f"{base}/projects/{quote(project_id)}/wiki/{quote(wiki_title, safe='')}")
    body = body.replace("{{files_url}}", f"{base}/projects/{quote(project_id)}/files")
    custom_content = bool((mail_subject or "").strip() or (mail_body or "").strip())
    send_release_email(
        settings,
        to_addrs=to_addrs,
        cc_addrs=cc_addrs,
        subject=subject,
        body=body,
        attachments=file_rows,
        apply_template_scope=not custom_content,
    )
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


@app.post("/api/auth/login", response_model=LoginResponse)
def api_login(payload: LoginRequest, response: Response) -> LoginResponse:
    base_url = default_base_url()
    auth_mode = payload.auth_mode or "password"
    username = payload.username.strip()
    api_key = payload.api_key.strip()
    if auth_mode == "api_key" and not api_key:
        raise _json_error("请填写 API Key")
    if auth_mode != "api_key" and (not username or not payload.password):
        raise _json_error("请填写用户名和密码")

    client = RedmineClient(base_url, username, payload.password, api_key=api_key, auth_mode=auth_mode)
    account = client.test_login()
    projects = client.list_projects()
    user = account.get("user", {})
    user_login = user.get("login") or username or "api-key"
    is_admin = bool(user.get("admin", False))
    projects = _visible_projects_for_user(client, projects, is_admin)
    session = {
        "connected": True,
        "base_url": base_url,
        "auth_mode": auth_mode,
        "username": username,
        "password": payload.password,
        "api_key": api_key,
        "user_login": user_login,
        "user_key": _user_key(base_url, str(user_login)),
        "is_admin": is_admin,
        "projects": projects,
    }
    sid = uuid.uuid4().hex
    SESSIONS[sid] = session
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax")
    store_login(base_url, username, payload.password, payload.remember, auth_mode=auth_mode, api_key=api_key)
    return _public_session(session)


@app.get("/api/auth/me", response_model=LoginResponse)
def api_me(session: Dict[str, Any] = Depends(_current_session), client: RedmineClient = Depends(_current_client)) -> LoginResponse:
    if not session.get("is_admin"):
        session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
    return _public_session(session)


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response) -> Dict[str, bool]:
    sid = request.cookies.get(SESSION_COOKIE, "")
    SESSIONS.pop(sid, None)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/projects")
def api_projects(session: Dict[str, Any] = Depends(_current_session), client: RedmineClient = Depends(_current_client)) -> List[Dict[str, Any]]:
    if not session.get("is_admin"):
        session["projects"] = _visible_projects_for_user(client, session.get("projects", []), False)
    return session.get("projects", [])


@app.get("/api/projects/{project_id}/release-categories")
def api_project_release_categories(project_id: str, client: RedmineClient = Depends(_current_client)) -> Dict[str, Any]:
    try:
        profile = IndexSync(client, project_id).discover_profile()
    except RedmineError:
        return {"mode": "", "categories": []}
    return {
        "mode": profile.mode,
        "categories": [
            {"key": category.key, "title": category.title}
            for category in profile.categories
        ],
    }


@app.get("/api/releases")
def api_releases(
    project_id: str = Query(...),
    product_line: str = Query(""),
    client: RedmineClient = Depends(_current_client),
) -> List[Dict[str, Any]]:
    return _list_release_rows(client, project_id, product_line)


@app.get("/api/releases/detail")
def api_release_detail(
    project_id: str = Query(...),
    wiki_title: str = Query(...),
    client: RedmineClient = Depends(_current_client),
) -> Dict[str, Any]:
    page = client.get_wiki_page(project_id, wiki_title)
    if not page:
        raise _json_error("未找到版本页面", 404)
    parsed = parse_release_page(wiki_title, page.get("text", ""))
    return {**parsed, "wiki_title": wiki_title, "files_info": format_release_files(parsed.get("files", []))}


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
    logs.append(f"开始{action}：项目 {project_id}")
    items = [line.strip() for line in changelog.splitlines() if line.strip()]
    if not items:
        raise _json_error("请填写至少一条变更说明")
    logs.append(f"变更说明校验通过：{len(items)} 条")

    file_rows: List[Tuple[str, str, bytes]] = []
    for upload in files or []:
        content = await upload.read()
        if upload.filename and content:
            file_rows.append((upload.filename, "", content))
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
    except RedmineError as exc:
        logs.append(f"{action}失败：{exc}")
        return JSONResponse(status_code=400, content={"detail": str(exc), "logs": logs})

    notice_message = ""
    if notice_enabled:
        try:
            scope = _normalize_mail_scope(mail_scope)
            to_addrs = split_emails(mail_to)
            cc_addrs = split_emails(mail_cc)
            logs.append(f"邮件通知已启用：{_mail_scope_label(scope)}，收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个")
            notice_message = _send_release_notice(
                session=session,
                client=client,
                project_id=project_id,
                wiki_title=title,
                version_name=version_name.strip(),
                release_date=release_date.strip(),
                commit=commit.strip(),
                product_line=product_line.strip(),
                changelog_items=items,
                file_rows=file_rows,
                mail_scope=scope,
                mail_to=to_addrs,
                mail_cc=cc_addrs,
                mail_subject=mail_subject,
                mail_body=mail_body,
            )
            logs.append(notice_message)
        except EmailSendError as exc:
            notice_message = f"邮件发送失败：{exc}"
            logs.append(notice_message)
    else:
        logs.append("邮件通知未启用，跳过发送")

    releases = _list_release_rows(client, project_id, product_line.strip())
    logs.append(f"刷新版本列表完成：返回 {len(releases)} 条")
    logs.append(f"{action}完成：{title}")
    return {"ok": True, "title": title, "notice_message": notice_message, "releases": releases, "logs": logs}


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


@app.put("/api/mail/admin-settings")
def api_save_admin_mail_settings(payload: AdminMailSettingsRequest, session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, bool]:
    _require_admin(session)
    store_email_server_settings(
        MAIL_SCOPE_INTERNAL,
        smtp_host=payload.internal_server.smtp_host,
        smtp_port=payload.internal_server.smtp_port,
        smtp_from=payload.internal_server.smtp_from,
        use_tls=payload.internal_server.use_tls,
    )
    store_email_server_settings(
        MAIL_SCOPE_EXTERNAL,
        smtp_host=payload.external_server.smtp_host,
        smtp_port=payload.external_server.smtp_port,
        smtp_from="",
        use_tls=payload.external_server.use_tls,
    )
    contacts = payload.internal_contacts.contacts or _merge_contact_lists(
        payload.internal_contacts.contacts_to,
        payload.internal_contacts.contacts_cc,
    )
    store_internal_contact_settings(contacts=contacts)
    return {"ok": True}


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


@app.post("/api/legacy-migration/preview")
def api_preview_legacy_migration(payload: LegacyMigrationRequest, client: RedmineClient = Depends(_current_client)) -> Dict[str, Any]:
    return LegacyChangelogMigrator(client, payload.project_id, payload.entry_pages).preview()


@app.post("/api/legacy-migration/execute")
def api_execute_legacy_migration(
    payload: LegacyMigrationRequest,
    session: Dict[str, Any] = Depends(_current_session),
    client: RedmineClient = Depends(_current_client),
) -> Dict[str, Any]:
    _require_admin(session)
    return LegacyChangelogMigrator(client, payload.project_id, payload.entry_pages).execute()


@app.post("/api/legacy-migration/execute-job")
def api_start_legacy_migration_job(
    payload: LegacyMigrationRequest,
    session: Dict[str, Any] = Depends(_current_session),
) -> Dict[str, Any]:
    _require_admin(session)
    job_id = uuid.uuid4().hex
    with LEGACY_JOB_LOCK:
        LEGACY_MIGRATION_JOBS[job_id] = {
            "status": "running",
            "logs": [f"{_job_timestamp()} 准备执行旧项目升级"],
            "result": None,
            "error": "",
        }
    thread = threading.Thread(
        target=_run_legacy_migration_job,
        args=(job_id, payload, dict(session)),
        daemon=True,
    )
    thread.start()
    return _legacy_job_snapshot(job_id)


@app.get("/api/legacy-migration/jobs/{job_id}")
def api_get_legacy_migration_job(job_id: str, session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
    _require_admin(session)
    return _legacy_job_snapshot(job_id)


@app.get("/api/wiki-config/templates")
def api_wiki_templates() -> List[Any]:
    return TEMPLATE_CHOICES


@app.post("/api/wiki-config/generate")
def api_generate_wiki_config(payload: WikiConfigGenerateRequest) -> Dict[str, str]:
    text = build_config_template(payload.template_key or "single_list", payload.project_id)
    ok, msg = validate_config_text(text)
    return {"text": text, "message": msg if ok else msg}


@app.get("/api/wiki-config/{project_id}/refresh-preview")
def api_preview_wiki_refresh(project_id: str, client: RedmineClient = Depends(_current_client)) -> Dict[str, Any]:
    return IndexSync(client, project_id).preview_refresh_all()


@app.post("/api/wiki-config/{project_id}/refresh")
def api_refresh_wiki_index(project_id: str, client: RedmineClient = Depends(_current_client)) -> Dict[str, Any]:
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
def api_get_wiki_config(project_id: str, client: RedmineClient = Depends(_current_client)) -> Dict[str, str]:
    page = client.get_wiki_page(project_id, CONFIG_PAGE_TITLE)
    if not page:
        return {"text": "", "message": f"未找到 {CONFIG_PAGE_TITLE}"}
    text = page.get("text", "")
    ok, msg = validate_config_text(text)
    return {"text": text, "message": msg if ok else f"已读取，但{msg}"}


@app.post("/api/wiki-config/check")
def api_check_wiki_config(payload: WikiConfigCheckRequest) -> Dict[str, Any]:
    ok, msg = validate_config_text(payload.text or "")
    return {"ok": ok, "message": msg}


@app.put("/api/wiki-config/{project_id}")
def api_save_wiki_config(project_id: str, payload: WikiConfigSaveRequest, client: RedmineClient = Depends(_current_client)) -> Dict[str, str]:
    ok, msg = validate_config_text(payload.text or "")
    if not ok:
        raise _json_error(msg)
    client.put_wiki_page(project_id, CONFIG_PAGE_TITLE, payload.text, "release tool config update")
    return {"message": f"已保存到 {CONFIG_PAGE_TITLE}。{msg}"}


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
