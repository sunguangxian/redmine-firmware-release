"""发布流程通用 helper。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .publisher import ReleasePublisher
from .redmine_api import RedmineClient

RECENT_RELEASE_LIMIT = 50


def list_release_rows(client: RedmineClient, project_id: str, product_line: str = "") -> List[Dict[str, Any]]:
    releases = ReleasePublisher(client).list_releases(project_id)
    if product_line:
        releases = [item for item in releases if item.get("product_line") == product_line]
    return releases[:RECENT_RELEASE_LIMIT]


def validate_release_preflight(
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
