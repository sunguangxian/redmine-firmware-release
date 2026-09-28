"""把测试问题表转成 Redmine 问题，并在确认后创建。"""

from __future__ import annotations

import re
from typing import Any

from .issue_sheet import IssueSheetError, ParsedIssue, ParsedWorkbook, parse_issue_workbook
from .redmine_api import RedmineClient, RedmineError


class IssueImportError(IssueSheetError):
    pass


ISSUE_SCAN_LIMIT = 5000


def preview_issue_sheet(
    client: RedmineClient,
    *,
    filename: str,
    content: bytes,
    project_id: str,
    year: int | None = None,
) -> dict[str, Any]:
    parsed = parse_issue_workbook(filename, content, year=year)
    context = project_import_context(client, project_id)
    suggested = _match_version(context["versions"], parsed.suggested_version)
    rows = [_issue_row(item, context["existing"]) for item in parsed.issues]
    duplicate_count = sum(1 for row in rows if row["duplicate"])
    return {
        "ok": True,
        "filename": parsed.filename,
        "context": _public_context(parsed),
        "suggested_version": suggested,
        "warnings": [*parsed.warnings, *context["warnings"]],
        "skipped_sheets": parsed.skipped_sheets,
        "used_sheets": parsed.used_sheets,
        "issues": rows,
        "counts": {
            "total": len(rows),
            "new": len(rows) - duplicate_count,
            "duplicate": duplicate_count,
        },
    }


def commit_issue_sheet(
    client: RedmineClient,
    *,
    filename: str,
    content: bytes,
    project_id: str,
    assigned_to_id: int,
    version_id: int,
    row_keys: list[str],
    year: int | None = None,
) -> dict[str, Any]:
    if not assigned_to_id:
        raise IssueImportError("请选择指派人")
    if not version_id:
        raise IssueImportError("请选择目标版本")
    selected = [key for key in row_keys if key]
    if not selected:
        raise IssueImportError("请至少选择一条问题")
    parsed = parse_issue_workbook(filename, content, year=year)
    context = project_import_context(client, project_id)
    version = next((item for item in context["versions"] if item["id"] == version_id), None)
    if version is None:
        raise IssueImportError("目标版本不在该项目中")
    assignee = next((item for item in context["assignees"] if item["id"] == assigned_to_id), None)
    if assignee is None:
        raise IssueImportError("指派用户不是该项目成员，无法指派")
    by_key = {item.row_key: item for item in parsed.issues}
    missing = [key for key in selected if key not in by_key]
    if missing:
        raise IssueImportError("选择的问题与表格不一致，请重新解析后再导入")
    chosen = [by_key[key] for key in selected]
    _require_mappings(chosen, context)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: dict[str, Any] | None = None
    for issue in chosen:
        key = _subject_key(issue.subject)
        existing = context["existing"].get(key)
        if existing:
            skipped.append(
                {
                    "row_key": issue.row_key,
                    "subject": issue.subject,
                    "reason": f"已存在 #{existing['id']}",
                }
            )
            continue
        fields: dict[str, Any] = {
            "tracker_id": context["tracker_ids"][issue.tracker_name],
            "subject": issue.subject,
            "description": issue.description,
            "priority_id": context["priority_ids"][issue.priority_name],
            "assigned_to_id": assigned_to_id,
            "fixed_version_id": version_id,
        }
        if issue.found_on:
            fields["start_date"] = issue.found_on
        try:
            created_issue = client.create_issue(project_id, fields)
        except RedmineError as exc:
            failed = {"row_key": issue.row_key, "subject": issue.subject, "error": str(exc)}
            break
        issue_id = int(created_issue.get("id") or 0)
        created.append(
            {
                "id": issue_id,
                "subject": issue.subject,
                "url": f"{client.base_url}/issues/{issue_id}",
            }
        )
        context["existing"][key] = {"id": issue_id, "version": version["name"]}
    return {
        "ok": failed is None,
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "version": version,
        "assignee": assignee,
    }


def project_import_options(client: RedmineClient, project_id: str) -> dict[str, Any]:
    context = project_import_context(client, project_id)
    return {
        "versions": context["versions"],
        "assignees": context["assignees"],
        "warnings": context["warnings"],
    }


def project_import_context(client: RedmineClient, project_id: str) -> dict[str, Any]:
    versions = [
        {
            "id": int(item.get("id") or 0),
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or ""),
        }
        for item in client.list_versions(project_id)
        if item.get("id")
    ]
    directory = _user_directory(client)
    assignees = _assignees(client.list_memberships(project_id), directory)
    priority_ids = {
        str(item.get("name") or ""): int(item["id"])
        for item in client.list_issue_priorities()
        if item.get("id") and item.get("name") and item.get("active", True)
    }
    project = client.get_project(project_id, include="trackers")
    tracker_ids = {
        str(item.get("name") or ""): int(item["id"])
        for item in (project.get("trackers") or [])
        if item.get("id") and item.get("name")
    }
    existing: dict[str, dict[str, Any]] = {}
    raw_issues = client.list_issues(project_id, limit_cap=ISSUE_SCAN_LIMIT)
    for item in raw_issues:
        subject = str(item.get("subject") or "")
        key = _subject_key(subject)
        if not key or key in existing:
            continue
        version = item.get("fixed_version") or {}
        existing[key] = {
            "id": int(item.get("id") or 0),
            "version": str(version.get("name") or ""),
        }
    warnings: list[str] = []
    if len(raw_issues) >= ISSUE_SCAN_LIMIT:
        warnings.append(f"项目问题超过 {ISSUE_SCAN_LIMIT} 条，只比对了前 {ISSUE_SCAN_LIMIT} 条标题")
    return {
        "versions": versions,
        "assignees": assignees,
        "priority_ids": priority_ids,
        "tracker_ids": tracker_ids,
        "existing": existing,
        "warnings": warnings,
    }


def _issue_row(issue: ParsedIssue, existing: dict[str, dict[str, Any]]) -> dict[str, Any]:
    match = existing.get(_subject_key(issue.subject))
    return {
        "row_key": issue.row_key,
        "sheet": issue.sheet,
        "excel_row": issue.excel_row,
        "seq": issue.seq,
        "seq_note": issue.seq_note,
        "found_on": issue.found_on,
        "module": issue.module,
        "level": issue.level,
        "priority_name": issue.priority_name,
        "tracker_name": issue.tracker_name,
        "subject": issue.subject,
        "description": issue.description,
        "duplicate": bool(match),
        "existing_id": match["id"] if match else None,
        "existing_version": match["version"] if match else "",
    }


def _public_context(parsed: ParsedWorkbook) -> dict[str, Any]:
    return {
        "title": parsed.title,
        "software_version": parsed.software_version,
        "mcu": parsed.mcu,
        "extra_versions": [{"name": name, "value": value} for name, value in parsed.extra_versions],
        "sample": parsed.sample,
        "suggested_version": parsed.suggested_version,
    }


def _require_mappings(issues: list[ParsedIssue], context: dict[str, Any]) -> None:
    for issue in issues:
        if not issue.priority_name or issue.priority_name not in context["priority_ids"]:
            shown = issue.level or "（空）"
            raise IssueImportError(f"无法映射故障等级「{shown}」。请取消该行或先在 Redmine 中补齐优先级")
        if issue.tracker_name not in context["tracker_ids"]:
            raise IssueImportError(f"项目没有「{issue.tracker_name}」跟踪标签，无法导入")


def _assignees(memberships: list[dict[str, Any]], directory: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    assignees: list[dict[str, Any]] = []
    seen: set[int] = set()
    for membership in memberships:
        user = membership.get("user") or {}
        user_id = int(user.get("id") or 0)
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        merged = {**directory.get(user_id, {}), **user, "id": user_id}
        assignees.append({"id": user_id, "name": _assignee_label(merged), "login": str(merged.get("login") or "")})
    assignees.sort(key=lambda item: item["name"])
    return assignees


def _user_directory(client: RedmineClient) -> dict[int, dict[str, Any]]:
    try:
        users = client.list_users()
    except RedmineError:
        return {}
    return {int(user["id"]): user for user in users if user.get("id")}


def _assignee_label(user: dict[str, Any]) -> str:
    last = str(user.get("lastname") or "").strip()
    first = str(user.get("firstname") or "").strip()
    login = str(user.get("login") or "").strip()
    name = str(user.get("name") or "").strip()
    display = f"{last}{first}".strip() or name or login or str(user.get("id") or "")
    if login and login not in display:
        return f"{display}（{login}）"
    return display


def _match_version(versions: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = (name or "").strip()
    if not wanted:
        return None
    for version in versions:
        if version["name"] == wanted:
            return version
    folded = wanted.casefold()
    for version in versions:
        if version["name"].casefold() == folded:
            return version
    return None


def _subject_key(subject: str) -> str:
    return re.sub(r"\s+", "", subject or "").casefold()
