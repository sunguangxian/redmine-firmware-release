"""接口权限与历史数据可见性工具。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from fastapi import HTTPException


HistoryLoader = Callable[..., List[Dict[str, Any]]]


def visible_project_ids(session: Dict[str, Any]) -> set[str]:
    """返回当前会话前端可见的项目 identifier 集合。"""
    result: set[str] = set()
    for project in session.get("projects", []) or []:
        identifier = str(project.get("identifier") or "").strip()
        if identifier:
            result.add(identifier)
    return result


def require_project_access(session: Dict[str, Any], project_id: str) -> None:
    """检查当前用户是否允许访问指定项目。管理员默认放行。"""
    if session.get("is_admin"):
        return
    project_id = (project_id or "").strip()
    if not project_id:
        raise HTTPException(status_code=403, detail="普通用户必须指定项目")
    if project_id not in visible_project_ids(session):
        raise HTTPException(status_code=403, detail="无权访问该项目")


def clamp_history_limit(limit: int) -> int:
    try:
        value = int(limit or 50)
    except (TypeError, ValueError):
        value = 50
    return max(1, min(value, 200))


def list_visible_history(
    session: Dict[str, Any],
    *,
    project_id: str = "",
    wiki_title: str = "",
    limit: int = 50,
    loader: HistoryLoader,
) -> List[Dict[str, Any]]:
    """按项目权限过滤历史记录。

    管理员不带 project_id 时可查询全部；普通用户不带 project_id 时，
    汇总其可见项目的历史并按 id 倒序截断。
    """
    project_id = (project_id or "").strip()
    wiki_title = (wiki_title or "").strip()
    limited = clamp_history_limit(limit)

    if project_id:
        require_project_access(session, project_id)
        return loader(project_id=project_id, wiki_title=wiki_title, limit=limited)

    if session.get("is_admin"):
        return loader(project_id="", wiki_title=wiki_title, limit=limited)

    items: List[Dict[str, Any]] = []
    for visible_project in sorted(visible_project_ids(session)):
        items.extend(loader(project_id=visible_project, wiki_title=wiki_title, limit=limited))
    items.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
    return items[:limited]
