"""Release Notes 索引同步。

同步策略由当前项目 Wiki 页面 ``Release_Tool_Config`` 明确配置。

工具不再自动扫描并猜测 Wiki 结构：

- 项目没有 ``Release_Tool_Config`` 时，索引同步直接报错提示。
- 配置页没有 ``RELEASE_CONFIG_BEGIN`` / ``RELEASE_CONFIG_END`` 配置块时，索引同步直接报错提示。
- 配置有效时，才更新主页面、分类页面和 Release 详情页父页面。
- 如果页面中存在 ``<!-- RELEASE_SYNC_BEGIN -->`` / ``<!-- RELEASE_SYNC_END -->``，只替换标记区域。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .redmine_api import RELEASE_PAGE_RE, RedmineClient, RedmineError
from .release_page import parse_inline_releases, proj_tag_from_project
from .wiki_config import CONFIG_PAGE_TITLE, ConfigCategory, parse_release_wiki_config

SYNC_BEGIN = "<!-- RELEASE_SYNC_BEGIN -->"
SYNC_END = "<!-- RELEASE_SYNC_END -->"
MAIN_RECENT_LIMIT = 5

CATEGORY_META = {
    "Regular": {"title": "常规版本 (5X)", "hub": "Release_Notes_Regular"},
    "Trunking": {"title": "Trunking 集群", "hub": "Release_Notes_Trunking"},
    "Record": {"title": "Record 录音", "hub": "Release_Notes_Record"},
    "NP500": {"title": "NP500", "hub": "Release_Notes_NP500"},
}


@dataclass
class CategoryProfile:
    key: str
    title: str
    hub: str
    list_page: str


@dataclass
class WikiProfile:
    mode: str
    main_page: str
    categories: list[CategoryProfile]
    release_page_prefix: str = ""
    release_detail_mode: str = "inline"


class IndexSync:
    def __init__(self, client: RedmineClient, project_id: str):
        self.client = client
        self.project_id = project_id
        self._wiki_index: list[dict[str, Any]] | None = None
        self._page_cache: dict[str, dict[str, Any] | None] = {}
        self._profile_cache: WikiProfile | None = None

    def sync_after_publish(self, page_title: str, page_text: str) -> None:
        self._page_cache[page_title] = {"title": page_title, "text": page_text}
        profile = self.discover_profile()
        if self._is_inline_profile(profile):
            if profile.mode == "multi_list":
                self._refresh_main_preserving_manual_content(profile, self._build_items(profile))
            return
        items = self._build_items(profile)

        if profile.mode == "multi_list":
            category = self._categorize(page_title, page_text, categories=profile.categories)
            self._sync_categories(profile, [category], items, update_main=True)
            cat_profile = self._category_by_key(profile, category)
            if cat_profile:
                self.client.put_wiki_page(
                    self.project_id,
                    page_title,
                    page_text,
                    comment="release tool sync parent",
                    parent_title=cat_profile.hub,
                )
        else:
            self._refresh_single(profile, items)

    def refresh_all(self) -> int:
        profile = self.discover_profile()
        items = self._build_items(profile)
        if self._is_inline_profile(profile):
            if profile.mode == "multi_list" and items:
                self._refresh_main_preserving_manual_content(profile, items)
            return len(items)
        if not items:
            return 0

        if profile.mode == "multi_list":
            self._sync_categories(profile, [c.key for c in profile.categories], items, update_main=True, set_parents=True)
        else:
            self._refresh_single(profile, items)
        return len(items)

    def preview_refresh_all(self) -> dict[str, Any]:
        profile = self.discover_profile()
        items = self._build_items(profile)
        plan = self._build_refresh_plan(profile, items)
        return {
            "mode": profile.mode,
            "main_page": profile.main_page,
            "release_count": len(items),
            "categories": [
                {
                    "key": category.key,
                    "title": category.title,
                    "hub": category.hub,
                    "list_page": category.list_page,
                    "release_count": sum(1 for item in items if item["cat"] == category.key),
                }
                for category in profile.categories
            ],
            "pages_to_update": plan["pages_to_update"],
            "parents_to_update": plan["parents_to_update"],
            "uncategorized": plan["uncategorized"],
            "warnings": plan["warnings"],
        }

    def _build_refresh_plan(self, profile: WikiProfile, items: list[dict[str, Any]]) -> dict[str, Any]:
        pages_to_update: list[str] = []
        parents_to_update: list[dict[str, str]] = []
        uncategorized: list[dict[str, str]] = []
        warnings: list[str] = []

        def add_page(title: str) -> None:
            if title and title not in pages_to_update:
                pages_to_update.append(title)

        if not items:
            warnings.append("当前项目没有找到 Release 页面，执行重建不会更新索引。")
            return {
                "pages_to_update": [],
                "parents_to_update": [],
                "uncategorized": [],
                "warnings": warnings,
            }

        add_page(profile.main_page)
        if profile.mode == "multi_list":
            category_keys = {category.key for category in profile.categories}
            for category in profile.categories:
                add_page(category.list_page)
                if category.list_page != category.hub:
                    add_page(category.hub)

            for item in items:
                category = item["cat"]
                if category not in category_keys:
                    uncategorized.append(
                        {
                            "page": item["page"],
                            "version": item["ver"],
                            "date": item["date"],
                        }
                    )
                    continue
                cat_profile = self._category_by_key(profile, category)
                page = self._get_page(item["page"])
                current_parent = (page or {}).get("parent") or {}
                if cat_profile and current_parent.get("title") != cat_profile.hub:
                    parents_to_update.append(
                        {
                            "page": item["page"],
                            "from": current_parent.get("title", ""),
                            "to": cat_profile.hub,
                        }
                    )

            if uncategorized:
                warnings.append(
                    f"有 {len(uncategorized)} 个 Release 无法匹配当前分类配置，重建后不会进入分类列表。"
                )
        else:
            for item in items:
                page = self._get_page(item["page"])
                current_parent = (page or {}).get("parent") or {}
                if current_parent.get("title") != profile.main_page:
                    parents_to_update.append(
                        {
                            "page": item["page"],
                            "from": current_parent.get("title", ""),
                            "to": profile.main_page,
                        }
                    )

        return {
            "pages_to_update": pages_to_update,
            "parents_to_update": parents_to_update,
            "uncategorized": uncategorized,
            "warnings": warnings,
        }

    def discover_profile(self) -> WikiProfile:
        """从 Release_Tool_Config 读取索引结构；不再自动猜测。"""
        if self._profile_cache:
            return self._profile_cache

        config_page = self._get_page(CONFIG_PAGE_TITLE)
        if not config_page:
            raise RedmineError(
                f"当前项目缺少 Wiki 配置页：{CONFIG_PAGE_TITLE}。"
                "请先按模板创建该页面，再发布或刷新 Release 索引。"
            )

        config = parse_release_wiki_config(config_page.get("text", ""))
        if not config or not config.is_valid:
            raise RedmineError(
                f"Wiki 配置页 {CONFIG_PAGE_TITLE} 无效。"
                "请检查 RELEASE_CONFIG_BEGIN / RELEASE_CONFIG_END 中的 mode、main_page 和 categories。"
            )

        if config.mode == "single_list":
            profile = WikiProfile(
                mode="single_list",
                main_page=config.main_page,
                categories=[],
                release_page_prefix=config.release_page_prefix,
                release_detail_mode=config.release_detail_mode,
            )
        else:
            categories = [self._category_from_config(c) for c in config.categories]
            profile = WikiProfile(
                mode="multi_list",
                main_page=config.main_page,
                categories=categories,
                release_page_prefix=config.release_page_prefix,
                release_detail_mode=config.release_detail_mode,
            )

        self._profile_cache = profile
        return profile

    def _category_from_config(self, item: ConfigCategory) -> CategoryProfile:
        meta = CATEGORY_META.get(item.key, {})
        title = item.title or meta.get("title") or item.key
        hub = item.hub_page or meta.get("hub") or f"Release_Notes_{item.key}"
        list_page = item.list_page or hub
        return CategoryProfile(key=item.key, title=title, hub=hub, list_page=list_page)

    def _wiki_titles(self) -> set[str]:
        if self._wiki_index is None:
            self._wiki_index = self.client.get_wiki_index(self.project_id)
        return {p.get("title", "") for p in self._wiki_index if p.get("title")}

    def _release_titles(self) -> list[str]:
        pages = self._wiki_index if self._wiki_index is not None else self.client.get_wiki_index(self.project_id)
        if self._wiki_index is None:
            self._wiki_index = pages
        return [p["title"] for p in pages if RELEASE_PAGE_RE.match(p.get("title", ""))]

    def _build_items(self, profile: WikiProfile) -> list[dict[str, Any]]:
        if self._is_inline_profile(profile):
            return self._build_inline_items(profile)
        items = []
        for title in self._release_titles():
            page = self._get_page(title)
            if not page:
                continue
            text = page.get("text", "")
            tag = proj_tag_from_project(self.project_id, title)
            ver = self._extract_version(text, tag, title)
            date = self._extract_date(text, title)
            commit = self._extract_commit(text)
            summary = self._extract_summary(text, ver)
            cat = self._categorize(title, text, ver, commit, profile.categories)
            items.append(
                {
                    "cat": cat,
                    "ver": ver,
                    "date": date,
                    "page": title,
                    "summary": summary,
                }
            )
        return items

    def _is_inline_profile(self, profile: WikiProfile) -> bool:
        return getattr(profile, "release_detail_mode", "inline") == "inline"

    def _build_inline_items(self, profile: WikiProfile) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        containers = (
            [(category.key, category.list_page) for category in profile.categories]
            if profile.mode == "multi_list"
            else [("", profile.main_page)]
        )
        for category_key, container in containers:
            page = self._get_page(container)
            if not page:
                continue
            for item in parse_inline_releases(page.get("text", ""), container):
                text = item.get("text", "")
                category = category_key or self._categorize(
                    item["title"],
                    text,
                    item["version"],
                    self._extract_commit(text),
                    profile.categories,
                )
                result.append(
                    {
                        "cat": category,
                        "ver": item["version"],
                        "date": item["date"],
                        "page": item["title"],
                        "container_page": container,
                        "block_id": item.get("block_id", ""),
                        "summary": item["summary"],
                        "product_line": item.get("product_line", ""),
                    }
                )
        return result

    def inline_container_for_release(self, profile: WikiProfile, page_title: str, page_text: str) -> str:
        if profile.mode != "multi_list":
            return profile.main_page
        category = self._categorize(page_title, page_text, categories=profile.categories)
        for item in profile.categories:
            if item.key == category:
                return item.list_page
        raise RedmineError("无法按当前分类配置确定内联版本应写入哪个列表页。")

    def _sync_categories(
        self,
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
                [i for i in items if i["cat"] == category],
                key=lambda x: x["date"],
                reverse=True,
            )
            if not group:
                continue

            lines = self._format_release_lines(group)
            list_fallback = (
                f"{SYNC_BEGIN}\n{lines}\n{SYNC_END}\n"
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
            self._refresh_main_preserving_manual_content(profile, items)

    def _refresh_single(self, profile: WikiProfile, items: list[dict[str, Any]] | None = None) -> int:
        items = items or self._build_items(profile)
        if not items:
            return 0
        sorted_items = sorted(items, key=lambda x: x["date"], reverse=True)
        lines = self._format_release_lines(sorted_items)
        tag = proj_tag_from_project(self.project_id, items[0]["page"])
        fallback = (
            f"# Release Notes\n\n"
            f"{tag} 固件版本发布记录。固件 bin 存放在 "
            f"[项目文件](/projects/{self.project_id}/files)，Wiki 仅记录变更。\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"{lines}"
        )
        page = self._get_page(profile.main_page)
        current = (page or {}).get("text", "")
        new_text = self._replace_generated_region(current, lines, "版本列表") if current else fallback
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

    def _put_generated_page(
        self,
        title: str,
        generated: str,
        comment: str,
        fallback_text: str,
        section_title: str,
        parent_title: str | None = None,
    ) -> None:
        page = self._get_page(title)
        current = (page or {}).get("text", "")
        if not current:
            new_text = fallback_text
        else:
            new_text = self._replace_generated_region(current, generated, section_title)
        self.client.put_wiki_page(self.project_id, title, new_text, comment, parent_title=parent_title)
        self._page_cache[title] = {"title": title, "text": new_text}

    def _replace_generated_region(self, text: str, generated: str, section_title: str) -> str:
        if SYNC_BEGIN in text and SYNC_END in text:
            return re.sub(
                rf"{re.escape(SYNC_BEGIN)}.*?{re.escape(SYNC_END)}",
                f"{SYNC_BEGIN}\n{generated}\n{SYNC_END}",
                text,
                flags=re.S,
            )

        replaced = self._replace_section(text, section_title, generated)
        if replaced != text:
            return replaced

        return text.rstrip() + f"\n\n{SYNC_BEGIN}\n{generated}\n{SYNC_END}\n"

    def _replace_section(self, text: str, section_title: str, generated: str) -> str:
        heading_re = re.compile(
            rf"(?P<head>^(?:#+\s*|h[1-6]\.\s*){re.escape(section_title)}\s*$)",
            re.M,
        )
        match = heading_re.search(text)
        if not match:
            return text

        first_generated_line = generated.lstrip().splitlines()[0] if generated.strip() else ""
        generated_has_heading = bool(heading_re.match(first_generated_line))
        start = match.start() if generated_has_heading or section_title == "版本列表" else match.end()

        if generated_has_heading:
            end = len(text)
        else:
            next_heading = re.search(r"^(?:#+\s+|h[1-6]\.\s+).+$", text[match.end():], re.M)
            end = match.end() + next_heading.start() if next_heading else len(text)

        return text[:start].rstrip() + "\n\n" + generated.rstrip() + "\n" + text[end:].lstrip("\n")

    def _format_release_lines(self, items: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- [[{i.get('container_page') or i['page']}|{i['ver']} ({i['date']})]] - {i['summary']}" for i in items
        )

    def _build_category_page(self, profile: WikiProfile, category: CategoryProfile, list_text: str) -> str:
        return (
            f"# {category.title}\n\n"
            f"[[{profile.main_page}|← 返回 Release Notes]]\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"{list_text}"
        )

    def _build_category_hub(self, profile: WikiProfile, category: CategoryProfile) -> str:
        return (
            f"# {category.title}\n\n"
            f"[[{profile.main_page}|返回 Release Notes]]\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"{{{{include({category.list_page})}}}}"
        )

    def _build_main(self, profile: WikiProfile, items: list[dict[str, Any]]) -> str:
        generated = self._build_main_generated(profile, items)
        return self._build_main_fallback(profile, items, generated)

    def _build_main_generated(self, profile: WikiProfile, items: list[dict[str, Any]]) -> str:
        lines = ["## Product Lines", ""]
        for category in profile.categories:
            count = sum(1 for i in items if i["cat"] == category.key)
            suffix = f" ({count})" if count else ""
            lines.append(f"- [[{category.hub}|{category.title}]]{suffix}")
        lines.append("")
        for category in profile.categories:
            group = sorted(
                [i for i in items if i["cat"] == category.key],
                key=lambda x: x["date"],
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

    def _build_main_fallback(self, profile: WikiProfile, items: list[dict[str, Any]], generated: str) -> str:
        tag = proj_tag_from_project(self.project_id, items[0]["page"] if items else None)
        return (
            f"# Release Notes\n\n"
            f"{tag} firmware release index. Firmware binaries are stored in "
            f"[project files](/projects/{self.project_id}/files); this Wiki keeps release notes and category indexes.\n\n"
            f"> Version lists are maintained by the release tool.\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"{generated}"
        )

    def _refresh_main_preserving_manual_content(self, profile: WikiProfile, items: list[dict[str, Any]]) -> None:
        generated = self._build_main_generated(profile, items)
        fallback = self._build_main_fallback(profile, items, generated)
        page = self._get_page(profile.main_page)
        current = (page or {}).get("text", "")
        if self._is_inline_profile(profile):
            current = self._clean_inline_main_text(current)
        new_text = self._replace_generated_region(current, generated, "Product Lines") if current else fallback
        self.client.put_wiki_page(self.project_id, profile.main_page, new_text, comment="auto sync main counts")
        self._page_cache[profile.main_page] = {"title": profile.main_page, "text": new_text}

    def _clean_inline_main_text(self, text: str) -> str:
        cleaned = re.sub(r"(?m)^>\s*Version lists are maintained by the release tool in the `\*_List` pages\.\s*\r?\n?", "", text or "")
        if SYNC_BEGIN in cleaned:
            before, after = cleaned.split(SYNC_BEGIN, 1)
            before = re.sub(r"(?ms)^## Product Lines\s*$.*\Z", "", before).rstrip()
            cleaned = f"{before}\n\n{SYNC_BEGIN}{after}" if before else f"{SYNC_BEGIN}{after}"
        return self._dedupe_toc(cleaned)

    def _dedupe_toc(self, text: str) -> str:
        seen = False

        def repl(match: re.Match[str]) -> str:
            nonlocal seen
            if seen:
                return ""
            seen = True
            return match.group(0).strip()

        return re.sub(r"(?m)^\s*\{\{>toc\}\}\s*$", repl, text or "")

    def _category_by_key(self, profile: WikiProfile, key: str) -> CategoryProfile | None:
        for category in profile.categories:
            if category.key == key:
                return category
        return None

    def _categorize(
        self,
        page_title: str,
        text: str,
        ver: str | None = None,
        commit: str | None = None,
        categories: list[CategoryProfile] | None = None,
    ) -> str:
        ver = ver or self._extract_version(text, proj_tag_from_project(self.project_id, page_title), page_title)
        commit = commit or self._extract_commit(text)
        product_line = self._extract_product_line(text)
        categories = categories or []
        configured = self._match_configured_category(product_line, page_title, categories)
        if configured:
            return configured
        if categories and product_line.strip():
            return ""

        legacy = self._legacy_category(page_title, text, ver, commit, product_line)
        if not categories:
            return legacy
        if any(category.key == legacy for category in categories):
            return legacy
        if len(categories) == 1:
            return categories[0].key
        return ""

    def _match_configured_category(
        self,
        product_line: str,
        page_title: str,
        categories: list[CategoryProfile],
    ) -> str:
        product_key = self._category_match_key(product_line)
        title_key = self._category_match_key(page_title)
        for category in categories:
            for candidate in (category.key, category.title):
                key = self._category_match_key(candidate)
                if not key:
                    continue
                if product_key == key:
                    return category.key
            for candidate in (category.hub, category.list_page):
                key = self._category_match_key(candidate)
                if key and key in title_key:
                    return category.key
        return ""

    def _category_match_key(self, value: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (value or "").lower())

    def _legacy_category(
        self,
        page_title: str,
        text: str,
        ver: str,
        commit: str,
        product_line: str,
    ) -> str:
        if "NP500" in product_line or "_NP500_FW_" in page_title:
            return "NP500"
        if "Trunking" in product_line or "集群" in product_line:
            return "Trunking"
        if "Record" in product_line or "录音" in product_line:
            return "Record"
        if re.match(r"V5\.4\.7\.", ver, re.I):
            return "Trunking"
        if re.search(r"Record|录音", commit) or (
            re.search(r"录音", text) and not re.match(r"V5\.4", ver, re.I)
        ):
            return "Record"
        return "Regular"

    def _extract_product_line(self, text: str) -> str:
        for pattern in (
            r"\*\*(?:产品线|Product Line|Product line):\*\*\s*([^\r\n]+)",
            r"\*\*(?:分类|Category):\*\*\s*([^\r\n]+)",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_version(self, text: str, tag: str, title: str = "") -> str:
        m = re.search(rf"# Release {re.escape(tag)} (?:NP500 )?FW ([^\r\n]+)", text, re.I)
        if not m:
            m = re.search(r"# Release [A-Za-z0-9_+-]+(?: NP500)? FW ([^\r\n]+)", text, re.I)
        if not m:
            m = re.search(r"^#{1,2}\s+\[([^\]\r\n]+)\]\([^)]+\)", text, re.I | re.M)
        if not m:
            m = re.search(r"^#{1,2}\s+(V[^\s\r\n]+)", text, re.I | re.M)
        if m:
            return m.group(1).strip()
        if "_FW_" in title:
            suffix = title.split("_FW_", 1)[1]
            return "V" + suffix.replace("_", ".").lstrip("Vv")
        return "?"

    def _extract_date(self, text: str, title: str = "") -> str:
        m = re.search(r"\*\*[^*:]+:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        title_date = re.search(r"_(\d{8})$", title)
        if title_date:
            raw = title_date.group(1)
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        return "0000-01-01"

    def _extract_commit(self, text: str) -> str:
        m = re.search(r"\*\*Commit:\*\*\s*([^\r\n]+)", text)
        return m.group(1).strip() if m else ""

    def _extract_summary(self, text: str, ver: str) -> str:
        m = re.search(r"^1\.\s+(.+)$", text, re.M)
        return m.group(1).strip() if m else f"release {ver}"

    def _get_page(self, title: str) -> dict[str, Any] | None:
        if title not in self._page_cache:
            self._page_cache[title] = self.client.get_wiki_page(self.project_id, title)
        return self._page_cache[title]

    def _page_text(self, title: str) -> str:
        page = self._get_page(title)
        return (page or {}).get("text", "")
