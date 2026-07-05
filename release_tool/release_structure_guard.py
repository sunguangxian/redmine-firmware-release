"""发布前 Wiki 结构保护。

只有项目已经创建并配置有效的 Release_Tool_Config 后，才允许发布或编辑版本。
这样可以避免旧 Wiki 结构下误写 Version、Wiki 页面或附件。
"""

from __future__ import annotations

from typing import Any

from .index_sync import IndexSync, WikiProfile
from .redmine_api import RedmineClient, RedmineError
from .wiki_config import CONFIG_PAGE_TITLE


def ensure_release_structure_ready(
    client: RedmineClient,
    project_id: str,
    logs: list[str] | None = None,
) -> tuple[IndexSync, WikiProfile]:
    index_sync = IndexSync(client, project_id)
    try:
        profile = index_sync.discover_profile()
    except RedmineError as exc:
        message = (
            "当前项目仍是旧的 Wiki 结构，或没有完成 Release_Tool_Config 配置，"
            "已禁止版本发布或编辑，避免写入异常。"
            f"请先在项目 Wiki 创建/修复 {CONFIG_PAGE_TITLE}，或先执行旧项目升级后再发布。"
            f"原始错误：{exc}"
        )
        if logs is not None:
            logs.append(message)
        raise RedmineError(message) from exc

    if logs is not None:
        logs.append(f"Wiki 结构检查通过：{CONFIG_PAGE_TITLE}，模式 {profile.mode}")
    return index_sync, profile
