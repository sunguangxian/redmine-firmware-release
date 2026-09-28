"""管理员导入测试问题表。"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import Depends, FastAPI, File, Form, UploadFile

from .audit_log import record_audit
from .dependencies import _current_client, _current_session, _json_error
from .issue_import import commit_issue_sheet, preview_issue_sheet, project_import_options
from .issue_sheet import IssueSheetError
from .redmine_api import RedmineClient, RedmineError

MAX_SHEET_BYTES = 8 * 1024 * 1024


def register_issue_import_routes(app: FastAPI) -> None:
    if getattr(app.state, "issue_import_routes_registered", False):
        return
    app.state.issue_import_routes_registered = True

    @app.get("/api/issue-import/options")
    def api_issue_import_options(
        project_id: str,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_issue_import_admin(session)
        project_id = (project_id or "").strip()
        if not project_id:
            raise _json_error("请选择项目")
        try:
            return project_import_options(client, project_id)
        except RedmineError as exc:
            raise _json_error(str(exc)) from exc

    @app.post("/api/issue-import/preview")
    def api_issue_import_preview(
        project_id: str = Form(...),
        year: int = Form(0),
        file: UploadFile = File(...),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_issue_import_admin(session)
        filename, content = _read_sheet(file)
        try:
            return preview_issue_sheet(
                client,
                filename=filename,
                content=content,
                project_id=project_id.strip(),
                year=year or None,
            )
        except IssueSheetError as exc:
            raise _json_error(str(exc)) from exc
        except RedmineError as exc:
            raise _json_error(str(exc)) from exc

    @app.post("/api/issue-import/commit")
    def api_issue_import_commit(
        project_id: str = Form(...),
        assigned_to_id: int = Form(...),
        version_id: int = Form(...),
        row_keys_json: str = Form("[]"),
        year: int = Form(0),
        file: UploadFile = File(...),
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_issue_import_admin(session)
        filename, content = _read_sheet(file)
        try:
            row_keys = json.loads(row_keys_json or "[]")
        except json.JSONDecodeError as exc:
            raise _json_error("所选问题无法解析，请重新预览") from exc
        if not isinstance(row_keys, list) or any(not isinstance(item, str) for item in row_keys):
            raise _json_error("所选问题无法解析，请重新预览")
        try:
            result = commit_issue_sheet(
                client,
                filename=filename,
                content=content,
                project_id=project_id.strip(),
                assigned_to_id=assigned_to_id,
                version_id=version_id,
                row_keys=row_keys,
                year=year or None,
            )
        except IssueSheetError as exc:
            raise _json_error(str(exc)) from exc
        except RedmineError as exc:
            raise _json_error(str(exc)) from exc
        record_audit(
            actor=str(session.get("user_login") or ""),
            action="issue_import",
            target_type="project",
            target_id=project_id.strip(),
            details={
                "filename": filename,
                "version_id": version_id,
                "assigned_to_id": assigned_to_id,
                "created_ids": [item["id"] for item in result["created"]],
                "skipped": len(result["skipped"]),
                "ok": result["ok"],
            },
        )
        return result


def _require_issue_import_admin(session: Dict[str, Any]) -> None:
    if not session.get("is_admin"):
        raise _json_error("只有 Redmine 管理员可以导入问题", 403)


def _read_sheet(file: UploadFile) -> tuple[str, bytes]:
    filename = (file.filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not filename.lower().endswith((".xls", ".xlsx")):
        raise _json_error("只支持 .xls 或 .xlsx 问题表")
    content = file.file.read()
    if not content:
        raise _json_error("上传的表格是空文件")
    if len(content) > MAX_SHEET_BYTES:
        raise _json_error("表格超过 8MB，无法导入")
    return filename, content
