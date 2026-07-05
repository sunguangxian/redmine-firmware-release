"""旧项目升级任务状态 helper。"""

from __future__ import annotations

from typing import Any, Dict

from .dependencies import _json_error
from .legacy_job_store import append_legacy_job_log, legacy_job_snapshot, update_legacy_job


def append_legacy_log(job_id: str, message: str) -> None:
    append_legacy_job_log(job_id, message)


def get_legacy_job_snapshot(job_id: str) -> Dict[str, Any]:
    snapshot = legacy_job_snapshot(job_id)
    if not snapshot:
        raise _json_error("旧项目升级任务不存在或已过期", 404)
    return snapshot


def set_legacy_job_state(job_id: str, **fields: Any) -> None:
    update_legacy_job(
        job_id,
        status=fields.get("status"),
        result=fields.get("result") if "result" in fields else None,
        error=fields.get("error") if "error" in fields else None,
    )
