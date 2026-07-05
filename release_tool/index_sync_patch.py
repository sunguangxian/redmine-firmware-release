"""运行时修补 Release Notes 索引同步，避免覆盖手工维护内容。"""

from __future__ import annotations

from typing import Any

from .index_sync import MAIN_RECENT_LIMIT, IndexSync, WikiProfile, proj_tag_from_project

_PATCHED = False


def _build_main_generated(self: IndexSync, profile: WikiProfile, items: list[dict[str, Any]]) -> str:
    lines = ["## Product Lines", ""]
    for category in profile.categories:
        count = sum(1 for item in items if item["cat"] == category.key)
        suffix = f" ({count})" if count else ""
        lines.append(f"- [[{category.hub}|{category.title}]]{suffix}")
    lines.append("")
    for category in profile.categories:
        group = sorted(
            [item for item in items if item["cat"] == category.key],
            key=lambda item: item["date"],
            reverse=True,
        )
        if not group:
            continue
        lines.extend(
            [
                f"## {category.title}",
                "",
                f"[[{category.hub}|查看全部]]",
                "",
                self._format_release_lines(group[:MAIN_RECENT_LIMIT]),
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _build_main_fallback(self: IndexSync, profile: WikiProfile, items: list[dict[str, Any]], generated: str) -> str:
    tag = proj_tag_from_project(self.project_id, items[0]["page"] if items else None)
    return (
        f"# Release Notes\n\n"
        f"{tag} firmware release index. Firmware binaries are stored in "
        f"[project files](/projects/{self.project_id}/files); this Wiki keeps release notes and category indexes.\n\n"
        f"> Version lists are maintained by the release tool in the `*_List` pages.\n\n"
        f"--------------\n\n"
        f"{{{{>toc}}}}\n\n"
        f"{generated}"
    )


def _refresh_main_preserving_manual_content(self: IndexSync, profile: WikiProfile, items: list[dict[str, Any]]) -> None:
    generated = _build_main_generated(self, profile, items)
    fallback = _build_main_fallback(self, profile, items, generated)
    page = self._get_page(profile.main_page)
    current = (page or {}).get("text", "")
    if current:
        new_text = self._replace_generated_region(current, generated, "Product Lines")
    else:
        new_text = fallback
    self.client.put_wiki_page(self.project_id, profile.main_page, new_text, comment="auto sync main counts")
    self._page_cache[profile.main_page] = {"title": profile.main_page, "text": new_text}


def _sync_categories_patched(
    self: IndexSync,
    profile: WikiProfile,
    categories: list[str],
    items: list[dict[str, Any]] | None = None,
    update_main: bool = False,
    set_parents: bool = False,
) -> None:
    items = items or self._build_items(profile)
    if not items:
        return

    for category in categories:
        cat_profile = self._category_by_key(profile, category)
        if not cat_profile:
            continue
        group = sorted(
            [item for item in items if item["cat"] == category],
            key=lambda item: item["date"],
            reverse=True,
        )
        if not group:
            continue

        lines = self._format_release_lines(group)
        list_fallback = (
            f"<!-- RELEASE_SYNC_BEGIN -->\n{lines}\n<!-- RELEASE_SYNC_END -->\n"
            if cat_profile.list_page != cat_profile.hub
            else self._build_category_page(profile, cat_profile, lines)
        )
        self._put_generated_page(
            cat_profile.list_page,
            lines,
            comment="auto sync list",
            fallback_text=list_fallback,
            section_title="版本列表",
            parent_title=cat_profile.hub if cat_profile.list_page != cat_profile.hub else None,
        )

        if cat_profile.list_page != cat_profile.hub:
            hub_text = self._build_category_hub(profile, cat_profile)
            self.client.put_wiki_page(
                self.project_id,
                cat_profile.hub,
                hub_text,
                "auto sync category structure",
                parent_title=profile.main_page,
            )
            self._page_cache[cat_profile.hub] = {"title": cat_profile.hub, "text": hub_text}

        if set_parents:
            for item in group:
                page = self._get_page(item["page"])
                if page and (page.get("parent") or {}).get("title") != cat_profile.hub:
                    self.client.put_wiki_page(
                        self.project_id,
                        item["page"],
                        page["text"],
                        "set parent",
                        parent_title=cat_profile.hub,
                    )

    if update_main:
        _refresh_main_preserving_manual_content(self, profile, items)


def _refresh_single_patched(self: IndexSync, profile: WikiProfile, items: list[dict[str, Any]] | None = None) -> int:
    items = items or self._build_items(profile)
    if not items:
        return 0
    sorted_items = sorted(items, key=lambda item: item["date"], reverse=True)
    lines = self._format_release_lines(sorted_items)
    tag = proj_tag_from_project(self.project_id, items[0]["page"])
    fallback = (
        f"# Release Notes\n\n"
        f"{tag} 固件版本发布记录。固件 bin 存放在 "
        f"[项目文件](/projects/{self.project_id}/files)，Wiki 仅记录变更。\n\n"
        f"--------------\n\n"
        f"{{{{>toc}}}}\n\n"
        f"## 版本列表\n\n"
        f"{lines}"
    )
    page = self._get_page(profile.main_page)
    current = (page or {}).get("text", "")
    if current:
        new_text = self._replace_generated_region(current, lines, "版本列表")
    else:
        new_text = fallback
    self.client.put_wiki_page(self.project_id, profile.main_page, new_text, comment="Release Notes 索引")
    self._page_cache[profile.main_page] = {"title": profile.main_page, "text": new_text}

    for item in sorted_items:
        page = self._get_page(item["page"])
        if page and (page.get("parent") or {}).get("title") != profile.main_page:
            self.client.put_wiki_page(
                self.project_id,
                item["page"],
                page["text"],
                "set parent",
                parent_title=profile.main_page,
            )
    return len(items)


def apply_index_sync_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    IndexSync._sync_categories = _sync_categories_patched
    IndexSync._refresh_single = _refresh_single_patched
