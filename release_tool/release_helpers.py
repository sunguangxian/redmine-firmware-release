"""发布流程通用 helper。"""

from __future__ import annotations

from datetime import datetime
import os
import time
from typing import Any, Dict, List, Tuple

from .publisher import ReleasePublisher
from .redmine_api import RedmineClient


_RESERVED_WIKI_MARKERS = ("<!-- RELEASE_INLINE_BEGIN:", "<!-- RELEASE_INLINE_END:", "<!-- RELEASE_SYNC_BEGIN", "<!-- RELEASE_SYNC_END")

RECENT_RELEASE_LIMIT = 50
_RELEASE_CACHE: dict[Tuple[str, str], tuple[float, List[Dict[str, Any]]]] = {}


def release_cache_ttl_seconds() -> int:
    try:
        return max(0, int(os.environ.get("RELEASE_TOOL_RELEASE_CACHE_TTL", "30")))
    except ValueError:
        return 30


def invalidate_release_rows(project_id: str = "") -> None:
    normalized_project = (project_id or "").strip()
    if not normalized_project:
        _RELEASE_CACHE.clear()
        return
    for key in list(_RELEASE_CACHE):
        if key[1] == normalized_project:
            _RELEASE_CACHE.pop(key, None)


def _cache_key(client: RedmineClient, project_id: str) -> Tuple[str, str]:
    return (getattr(client, "base_url", ""), (project_id or "").strip())


def _copy_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in rows]


def list_release_rows(
    client: RedmineClient,
    project_id: str,
    product_line: str = "",
    *,
    use_cache: bool = False,
) -> List[Dict[str, Any]]:
    cache_key = _cache_key(client, project_id)
    ttl = release_cache_ttl_seconds()
    now = time.monotonic()
    if use_cache and ttl > 0:
        cached = _RELEASE_CACHE.get(cache_key)
        if cached and now - cached[0] <= ttl:
            releases = _copy_rows(cached[1])
        else:
            releases = ReleasePublisher(client).list_releases(project_id)
            _RELEASE_CACHE[cache_key] = (now, _copy_rows(releases))
    else:
        releases = ReleasePublisher(client).list_releases(project_id)

    if product_line:
        releases = [item for item in releases if item.get("product_line") == product_line]
        return releases
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
    fields = {
        "项目标识": project_id,
        "版本号": version_name,
        "Commit": commit,
        "变更说明": "\n".join(changelog_items),
    }
    for label, value in fields.items():
        if any(marker in value for marker in _RESERVED_WIKI_MARKERS) or "-->" in value:
            raise ValueError(f"{label}不能包含发布工具内部页面标记")
        if "\x00" in value:
            raise ValueError(f"{label}不能包含空字符")
    if "\r" in version_name or "\n" in version_name or len(version_name.strip()) > 128:
        raise ValueError("版本号不能换行且长度不能超过 128 个字符")
