"""FastAPI 应用共享入口。

本模块只保留全局 app、公共兼容导出和前端挂载。
具体业务接口由 app_factory 统一注册到独立 *_api 模块。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config_store import MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL
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
from .email_sender import EmailSettings
from .legacy_job_store import append_legacy_job_log, legacy_job_snapshot, update_legacy_job
from .mail_contact_helpers import (
    MAIL_SCOPES,
    contact_people,
    contacts_for_scope,
    mail_scope_label,
    merge_contact_lists,
    normalize_mail_scope,
)
from .mail_delivery_helpers import build_email_settings, send_release_notice, validate_notice_preflight
from .redmine_api import RedmineClient, RedmineError
from .release_helpers import RECENT_RELEASE_LIMIT, list_release_rows, validate_release_preflight
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
    return build_email_settings(session, scope)


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
    return validate_notice_preflight(session, mail_scope, mail_to, mail_cc, mail_subject, mail_body)


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
    return send_release_notice(
        session=session,
        client=client,
        project_id=project_id,
        wiki_title=wiki_title,
        version_name=version_name,
        file_rows=file_rows,
        mail_scope=mail_scope,
        mail_to=mail_to,
        mail_cc=mail_cc,
        mail_subject=mail_subject,
        mail_body=mail_body,
        send_type=send_type,
    )


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
