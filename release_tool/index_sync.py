"""Release Notes 索引同步。

同步策略以项目 Wiki 当前结构为准：

- 如果项目已经存在多个产品线页面，例如 ``Release_Notes_Regular``、
  ``Release_Notes_Trunking``，则按多分类结构同步。
- 如果项目只有一个 ``Release_Notes`` 页面和若干 ``Release_xxx_FW_xxx`` 页面，
  则按单列表结构同步。
- 如果页面中存在 ``<!-- RELEASE_SYNC_BEGIN -->`` / ``<!-- RELEASE_SYNC_END -->``，
  只替换标记区域。
- 如果没有标记，则尽量只替换“版本列表”或“产品线索引”章节，避免覆盖页面说明。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .redmine_api import RELEASE_PAGE_RE, RedmineClient
from .release_page import proj_tag_from_project

SYNC_BEGIN = "<!-- RELEASE_SYNC_BEGIN -->"
SYNC_END = "<!-- RELEASE_SYNC_END -->"

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


class IndexSync:
    def __init__(self, client: RedmineClient, project_id: str):
        self.client = client
        self.project_id = project_id
        self._wiki_index: list[dict[str, Any]] | None = None
        self._page_cache: dict[str, dict[str, Any] | None] = {}

    def sync_after_publish(self, page_title: str, page_text: str) -> None:
        # 发布页刚刚写入，先放入缓存，后续自动识别时能立即看到最新内容。
        self._page_cache[page_title] = {"title": page_title, "text": page_text}
        profile = self.discover_profile()
        items = self._build_items(profile)

        if profile.mode == "multi_list":
            category = self._categorize(page_title, page_text)
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
        if not items:
            return 0

        if profile.mode == "multi_list":
            self._sync_categories(profile, [c.key for c in profile.categories], items, update_main=True, set_parents=True)
        else:
            self._refresh_single(profile, items)
        return len(items)

    def discover_profile(self) -> WikiProfile:
        """从项目 Wiki 自动推断索引结构。"""
        titles = self._wiki_titles()
        release_titles = self._release_titles()
        main_page = self._discover_main_page(titles)
        main_text = self._page_text(main_page)

        categories = self._discover_categories(titles, main_text, release_titles)
        has_category_pages = any(c.hub in titles or c.list_page in titles for c in categories)
        main_has_category_refs = any(c.hub in main_text or c.list_page in main_text for c in categories)

        # 优先尊重已有 Wiki 结构：只要已经有产品线页面或主页面引用产品线页面，就认为是多分类。
        if categories and (has_category_pages or main_has_category_refs):
            return WikiProfile(mode="multi_list", main_page=main_page, categories=categories)

        # 没有明显产品线页面时，即使存在 Trunking / Record / NP500 版本，也按单列表处理，
        # 避免工具把 TP35 这类项目误拆成多页面结构。
        return WikiProfile(mode="single_list", main_page=main_page, categories=[])

    def _wiki_titles(self) -> set[str]:
        if self._wiki_index is None:
            self._wiki_index = self.client.get_wiki_index(self.project_id)
        return {p.get("title", "") for p in self._wiki_index if p.get("title")}

    def _release_titles(self) -> list[str]:
        pages = self._wiki_index if self._wiki_index is not None else self.client.get_wiki_index(self.project_id)
        if self._wiki_index is None:
            self._wiki_index = pages
        return [p["title"] for p in pages if RELEASE_PAGE_RE.match(p.get("title", ""))]

    def _discover_main_page(self, titles: set[str]) -> str:
        tag = self.project_id.upper()
        candidates = []
        preferred = [f"Changelog_for_{tag}", "Changelog_for_5X", "Release_Notes"]
        candidates.extend([p for p in preferred if p in titles])
        candidates.extend([t for t in titles if "release" in t.lower() or "changelog" in t.lower()])

        if not candidates:
            return "Release_Notes"

        scored: list[tuple[int, str]] = []
        for title in dict.fromkeys(candidates):
            text = self._page_text(title)
            score = 0
            if title == "Release_Notes":
                score += 3
            if title.startswith("Changelog_for_"):
                score += 4
            if re.search(r"Release Notes|版本列表|产品线索引", text, re.I):
                score += 4
            if re.search(r"Release_Notes_(Regular|Trunking|Record|NP500)", text):
                score += 6
            if re.search(r"\{\{include\(Release_Notes_", text):
                score += 6
            if re.search(r"\[\[Release_[^\]|]+", text):
                score += 2
            scored.append((score, title))

        scored.sort(reverse=True)
        return scored[0][1] if scored else candidates[0]

    def _discover_categories(
        self,
        titles: set[str],
        main_text: str,
        release_titles: list[str],
    ) -> list[CategoryProfile]:
        categories: list[CategoryProfile] = []
        detected_keys = {self._categorize(title, self._page_text(title)) for title in release_titles}

        for key, meta in CATEGORY_META.items():
            hub = meta["hub"]
            title = meta["title"]
            default_list = f"{hub}_List"

            if default_list in titles:
                list_page = default_list
            elif hub in titles:
                hub_text = self._page_text(hub)
                included = self._first_include_page(hub_text)
                list_page = included if included else hub
            else:
                list_page = default_list

            exists_or_referenced = (
                hub in titles
                or default_list in titles
                or hub in main_text
                or default_list in main_text
                or title in main_text
            )
            if exists_or_referenced or key in detected_keys:
                categories.append(CategoryProfile(key=key, title=title, hub=hub, list_page=list_page))

        return categories

    def _first_include_page(self, text: str) -> str | None:
        match = re.search(r"\{\{include\(([^)]+)\)\}\}", text)
        return match.group(1).strip() if match else None

    def _build_items(self, profile: WikiProfile) -> list[dict[str, Any]]:
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
            cat = self._categorize(title, text, ver, commit)
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
            self._put_generated_page(
                cat_profile.list_page,
                lines,
                comment="auto sync list",
                fallback_text=self._build_category_page(cat_profile, lines),
                section_title="版本列表",
            )

            if cat_profile.list_page != cat_profile.hub and not self._get_page(cat_profile.hub):
                hub_text = self._build_category_hub(cat_profile)
                self.client.put_wiki_page(self.project_id, cat_profile.hub, hub_text, "产品线索引")

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
            main = self._build_main(profile, items)
            self._put_generated_page(
                profile.main_page,
                main,
                comment="auto sync main counts",
                fallback_text=main,
                section_title="产品线索引",
            )

    def _refresh_single(self, profile: WikiProfile, items: list[dict[str, Any]] | None = None) -> int:
        items = items or self._build_items(profile)
        if not items:
            return 0
        lines = self._format_release_lines(sorted(items, key=lambda x: x["date"], reverse=True))
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
        self._put_generated_page(
            profile.main_page,
            lines,
            comment="Release Notes 索引",
            fallback_text=fallback,
            section_title="版本列表",
        )
        return len(items)

    def _put_generated_page(
        self,
        title: str,
        generated: str,
        comment: str,
        fallback_text: str,
        section_title: str,
    ) -> None:
        page = self._get_page(title)
        current = (page or {}).get("text", "")
        if not current:
            new_text = fallback_text
        else:
            new_text = self._replace_generated_region(current, generated, section_title)
        self.client.put_wiki_page(self.project_id, title, new_text, comment)
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
        start = match.start() if generated_has_heading else match.end()

        # 如果 generated 自己包含“产品线索引”标题，通常它还包含后续所有产品线章节，
        # 此时直接替换到页面末尾，避免旧分类章节残留或标题重复。
        if generated_has_heading:
            end = len(text)
        else:
            next_heading = re.search(r"^(?:#+\s+|h[1-6]\.\s+).+$", text[match.end():], re.M)
            end = match.end() + next_heading.start() if next_heading else len(text)

        return text[:start].rstrip() + "\n\n" + generated.rstrip() + "\n" + text[end:].lstrip("\n")

    def _format_release_lines(self, items: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- [[{i['page']}|{i['ver']} ({i['date']})]] - {i['summary']}" for i in items
        )

    def _build_category_page(self, category: CategoryProfile, list_text: str) -> str:
        return (
            f"# {category.title}\n\n"
            f"[[{self._discover_main_page(self._wiki_titles())}|← 返回 Release Notes]]\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"## 版本列表\n\n"
            f"{list_text}"
        )

    def _build_category_hub(self, category: CategoryProfile) -> str:
        return (
            f"# {category.title}\n\n"
            f"[[{self._discover_main_page(self._wiki_titles())}|← 返回 Release Notes]]\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"## 版本列表\n\n"
            f"{{{{include({category.list_page})}}}}"
        )

    def _build_main(self, profile: WikiProfile, items: list[dict[str, Any]]) -> str:
        tag = proj_tag_from_project(self.project_id, items[0]["page"] if items else None)
        lines = [
            "## 产品线索引",
            "",
        ]
        for category in profile.categories:
            count = sum(1 for i in items if i["cat"] == category.key)
            if count:
                lines.append(f"- [[{category.hub}|{category.title}]] ({count})")
        lines.append("")
        for category in profile.categories:
            if not any(i["cat"] == category.key for i in items):
                continue
            lines.extend(
                [
                    f"## {category.title}",
                    "",
                    f"[[{category.hub}|独立页面]]",
                    "",
                    f"{{{{include({category.list_page})}}}}",
                    "",
                ]
            )

        generated = "\n".join(lines).rstrip()
        current = self._page_text(profile.main_page)
        if current:
            return generated

        return (
            f"# Release Notes\n\n"
            f"{tag} 固件发布记录，按产品线分类。固件 bin 在 "
            f"[项目文件](/projects/{self.project_id}/files)，Wiki 仅记录变更。\n\n"
            f"> 版本列表由 `{{include(...)}}` 动态嵌入；通过版本发布工具保存后自动同步。\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"{generated}"
        )

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
    ) -> str:
        ver = ver or self._extract_version(text, proj_tag_from_project(self.project_id, page_title), page_title)
        commit = commit or self._extract_commit(text)
        product_line = self._extract_product_line(text)
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
        match = re.search(r"\*\*产品线:\*\*\s*([^\r\n]+)", text)
        return match.group(1).strip() if match else ""

    def _extract_version(self, text: str, tag: str, title: str = "") -> str:
        m = re.search(rf"# Release {re.escape(tag)} (?:NP500 )?FW ([^\r\n]+)", text, re.I)
        if not m:
            m = re.search(r"# Release [A-Za-z0-9]+(?: NP500)? FW ([^\r\n]+)", text, re.I)
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
