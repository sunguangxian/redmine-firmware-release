"""旧 Changelog 迁移接口，目标结构与版本管理的四种标准布局保持一致。"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .audit_log import record_audit
from .dependencies import _client_from_session, _current_client, _current_session, _require_admin
from .legacy_changelog_migrator import LegacyChangelogMigrator
from .legacy_job_helpers import append_legacy_log, get_legacy_job_snapshot, set_legacy_job_state
from .legacy_job_store import cleanup_legacy_jobs, create_legacy_job, fail_interrupted_legacy_jobs
from .redmine_api import RedmineClient
from .release_helpers import invalidate_release_rows

_LEGACY_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="legacy-migration")


class LegacyMigrationRequestV2(BaseModel):
    project_id: str
    entry_pages: List[str] = Field(default_factory=lambda: ["Changelog"])
    release_detail_mode: str = "auto"


def _make_migrator(
    client: RedmineClient,
    payload: LegacyMigrationRequestV2,
    log_callback=None,
) -> LegacyChangelogMigrator:
    return LegacyChangelogMigrator(
        client,
        payload.project_id,
        payload.entry_pages,
        log_callback=log_callback,
        release_detail_mode=payload.release_detail_mode,
    )


def _create_legacy_job(job_id: str, payload: LegacyMigrationRequestV2) -> None:
    cleanup_legacy_jobs()
    create_legacy_job(
        job_id,
        project_id=payload.project_id,
        entry_pages=payload.entry_pages,
        release_detail_mode=payload.release_detail_mode,
    )
    append_legacy_log(job_id, f"准备执行旧项目升级，版本模式：{payload.release_detail_mode or 'auto'}")


def _preview_with_mode(migrator: LegacyChangelogMigrator) -> Dict[str, Any]:
    return migrator.preview()


def _run_legacy_migration_job(job_id: str, payload: LegacyMigrationRequestV2, session: Dict[str, Any]) -> None:
    try:
        append_legacy_log(job_id, "后台任务已启动")
        client = _client_from_session(session)
        migrator = _make_migrator(
            client,
            payload,
            log_callback=lambda message: append_legacy_log(job_id, message),
        )
        result = migrator.execute()
        invalidate_release_rows(payload.project_id)
        append_legacy_log(job_id, result.get("message", "旧项目升级完成"))
        set_legacy_job_state(job_id, status="succeeded", result=result)
    except Exception as exc:
        append_legacy_log(job_id, f"执行失败：{exc}")
        set_legacy_job_state(job_id, status="failed", error=str(exc))


def register_legacy_migration_routes(app: FastAPI) -> None:
    if getattr(app.state, "legacy_migration_routes_registered", False):
        return
    app.state.legacy_migration_routes_registered = True
    fail_interrupted_legacy_jobs()

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
        record_audit(
            actor=session.get("user_login", ""),
            action="legacy_migration_execute",
            target_type="project",
            target_id=payload.project_id,
            details={"entry_pages": payload.entry_pages, "release_detail_mode": payload.release_detail_mode},
        )
        result = _make_migrator(client, payload).execute()
        invalidate_release_rows(payload.project_id)
        return result

    @app.post("/api/legacy-migration/execute-job")
    def api_start_legacy_migration_job(
        payload: LegacyMigrationRequestV2,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        _require_admin(session)
        job_id = uuid.uuid4().hex
        _create_legacy_job(job_id, payload)
        record_audit(
            actor=session.get("user_login", ""),
            action="legacy_migration_job_started",
            target_type="project",
            target_id=payload.project_id,
            details={
                "job_id": job_id,
                "entry_pages": payload.entry_pages,
                "release_detail_mode": payload.release_detail_mode,
            },
        )
        _LEGACY_JOB_EXECUTOR.submit(_run_legacy_migration_job, job_id, payload, dict(session))
        return get_legacy_job_snapshot(job_id)

    @app.get("/api/legacy-migration/jobs/{job_id}")
    def api_get_legacy_migration_job(job_id: str, session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
        _require_admin(session)
        cleanup_legacy_jobs()
        return get_legacy_job_snapshot(job_id)
