"""旧 Changelog 迁移接口。

支持按本次任务选择 release_detail_mode：
- auto：有旧配置则沿用旧配置，没有配置默认 inline
- inline：强制迁移为内联版本
- page：强制迁移为一版本一页
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .api_app import (
    LEGACY_JOB_LOCK,
    LEGACY_MIGRATION_JOBS,
    _append_legacy_job_log,
    _client_from_session,
    _current_client,
    _current_session,
    _legacy_job_snapshot,
    _require_admin,
    _set_legacy_job_state,
)
from .inline_release_patch import normalize_migration_detail_mode, selected_migration_detail_mode
from .legacy_changelog_migrator import LegacyChangelogMigrator
from .redmine_api import RedmineClient
from .release_page import extract_inline_release_block


class LegacyMigrationRequestV2(BaseModel):
    project_id: str
    entry_pages: List[str] = Field(default_factory=lambda: ["Changelog"])
    release_detail_mode: str = "auto"


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_legacy_routes(app: FastAPI) -> None:
    specs = [
        ("/api/legacy-migration/preview", "POST"),
        ("/api/legacy-migration/execute", "POST"),
        ("/api/legacy-migration/execute-job", "POST"),
        ("/api/legacy-migration/jobs/{job_id}", "GET"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def _make_migrator(
    client: RedmineClient,
    payload: LegacyMigrationRequestV2,
    log_callback=None,
) -> LegacyChangelogMigrator:
    migrator = LegacyChangelogMigrator(client, payload.project_id, payload.entry_pages, log_callback=log_callback)
    migrator.release_detail_mode = normalize_migration_detail_mode(payload.release_detail_mode)
    return migrator


def _legacy_inline_container(release: Any, *, single_list: bool) -> str:
    return "Release_Notes" if single_list else f"Release_Notes_{release.model}"


def _apply_inline_preview_counts(migrator: LegacyChangelogMigrator, preview: Dict[str, Any]) -> None:
    releases, _sources, _warnings = migrator.scan()
    categories = migrator._release_categories(releases)
    single_list = len(categories) == 1
    existing_blocks = 0
    new_blocks = 0
    page_cache: dict[str, str] = {}
    for release in releases:
        container = _legacy_inline_container(release, single_list=single_list)
        if container not in page_cache:
            page = migrator.client.get_wiki_page(migrator.project_id, container)
            page_cache[container] = (page or {}).get("text", "")
        block_id = release.wiki_title
        if extract_inline_release_block(page_cache[container], block_id):
            existing_blocks += 1
        else:
            new_blocks += 1
    preview["release_pages_to_create"] = new_blocks
    preview["existing_release_pages"] = existing_blocks


def _preview_with_mode(migrator: LegacyChangelogMigrator) -> Dict[str, Any]:
    preview = migrator.preview()
    detail_mode = selected_migration_detail_mode(migrator)
    preview["release_detail_mode"] = detail_mode
    preview["release_detail_mode_label"] = "内联模式" if detail_mode == "inline" else "一版本一页"
    preview["requested_release_detail_mode"] = normalize_migration_detail_mode(getattr(migrator, "release_detail_mode", "auto"))
    if detail_mode == "inline":
        preview["target_page_label"] = "承载页面"
        _apply_inline_preview_counts(migrator, preview)
    else:
        preview["target_page_label"] = "Release 明细页"
    return preview


def _run_legacy_migration_job(job_id: str, payload: LegacyMigrationRequestV2, session: Dict[str, Any]) -> None:
    try:
        _append_legacy_job_log(job_id, "后台任务已启动")
        client = _client_from_session(session)
        migrator = _make_migrator(
            client,
            payload,
            log_callback=lambda message: _append_legacy_job_log(job_id, message),
        )
        result = migrator.execute()
        _append_legacy_job_log(job_id, result.get("message", "旧项目升级完成"))
        _set_legacy_job_state(job_id, status="succeeded", result=result)
    except Exception as exc:
        _append_legacy_job_log(job_id, f"执行失败：{exc}")
        _set_legacy_job_state(job_id, status="failed", error=str(exc))


def register_legacy_migration_routes(app: FastAPI) -> None:
    if getattr(app.state, "legacy_migration_routes_registered", False):
        return
    app.state.legacy_migration_routes_registered = True
    _remove_existing_legacy_routes(app)

    @app.post("/api/legacy-migration/preview")
    def api_preview_legacy_migration(
        payload: LegacyMigrationRequestV2,
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        return _preview_with_mode(_make_migrator(client, payload))

    @app.post("/api/legacy-migration/execute")
    def api_execute_legacy_migration(
        payload: LegacyMigrationRequestV2,
        session: Dict[str, Any] = Depends(_current_session),
        client: RedmineClient = Depends(_current_client),
    ) -> Dict[str, Any]:
        _require_admin(session)
        return _make_migrator(client, payload).execute()

    @app.post("/api/legacy-migration/execute-job")
    def api_start_legacy_migration_job(
        payload: LegacyMigrationRequestV2,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        _require_admin(session)
        job_id = uuid.uuid4().hex
        with LEGACY_JOB_LOCK:
            LEGACY_MIGRATION_JOBS[job_id] = {
                "status": "running",
                "logs": [f"准备执行旧项目升级，版本模式：{normalize_migration_detail_mode(payload.release_detail_mode)}"],
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
