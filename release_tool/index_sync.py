"""Release Notes 索引同步。"""

from __future__ import annotations

import re
from typing import Any

from .redmine_api import RELEASE_PAGE_RE, RedmineClient
from .release_page import proj_tag_from_project

CATEGORY_META = {
    "Regular": {"title": "常规版本 (5X)", "hub": "Release_Notes_Regular"},
    "Trunking": {"title": "Trunking 集群", "hub": "Release_Notes_Trunking"},
    "Record": {"title": "Record 录音", "hub": "Release_Notes_Record"},
    "NP500": {"title": "NP500", "hub": "Release_Notes_NP500"},
}


class IndexSync:
    def __init__(self, client: RedmineClient, project_id: str):
        self.client = client
        self.project_id = project_id

    def sync_after_publish(self, page_title: str, page_text: str) -> None:
        if self._categorized():
            category = self._categorize(page_title, page_text)
            items = self._build_items()
            self._sync_categories([category], items, update_main=True)
            hub = CATEGORY_META[category]["hub"]
            self.client.put_wiki_page(
                self.project_id,
                page_title,
                page_text,
                comment="release tool sync parent",
                parent_title=hub,
            )
        else:
            self._refresh_flat()

    def refresh_all(self) -> int:
        if self._categorized():
            return self._refresh_categorized()
        return self._refresh_flat()

    def _release_titles(self) -> list[str]:
        pages = self.client.get_wiki_index(self.project_id)
        return [p["title"] for p in pages if RELEASE_PAGE_RE.match(p["title"])]

    def _categorized(self) -> bool:
        for title in self._release_titles():
            if "_NP500_FW_" in title:
                return True
            page = self.client.get_wiki_page(self.project_id, title)
            text = (page or {}).get("text", "")
            if re.search(r"^V5\.4\.7\.", text, re.M) or re.search(r"Record|录音", text):
                return True
        return False

    def _build_items(self) -> list[dict[str, Any]]:
        items = []
        for title in self._release_titles():
            page = self.client.get_wiki_page(self.project_id, title)
            if not page:
                continue
            text = page.get("text", "")
            tag = proj_tag_from_project(self.project_id, title)
            ver = self._extract_version(text, tag)
            date = self._extract_date(text)
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
        categories: list[str],
        items: list[dict[str, Any]] | None = None,
        update_main: bool = False,
        set_parents: bool = False,
    ) -> None:
        items = items or self._build_items()
        if not items:
            return

        for category in categories:
            meta = CATEGORY_META.get(category)
            if not meta:
                continue
            group = sorted(
                [i for i in items if i["cat"] == category],
                key=lambda x: x["date"],
                reverse=True,
            )
            if not group:
                continue

            list_page = f"{meta['hub']}_List"
            lines = "\n".join(
                f"- [[{i['page']}|{i['ver']} ({i['date']})]] - {i['summary']}" for i in group
            )
            self.client.put_wiki_page(self.project_id, list_page, lines, "auto sync list")

            if set_parents:
                for item in group:
                    page = self.client.get_wiki_page(self.project_id, item["page"])
                    if page and (page.get("parent") or {}).get("title") != meta["hub"]:
                        self.client.put_wiki_page(
                            self.project_id,
                            item["page"],
                            page["text"],
                            "set parent",
                            parent_title=meta["hub"],
                        )

        if update_main:
            main = self._build_main(items)
            self.client.put_wiki_page(self.project_id, "Release_Notes", main, "auto sync main counts")

    def _refresh_categorized(self) -> int:
        items = self._build_items()
        if not items:
            return 0

        self._sync_categories(list(CATEGORY_META.keys()), items, set_parents=True)

        for category, meta in CATEGORY_META.items():
            if not any(i["cat"] == category for i in items):
                continue
            list_page = f"{meta['hub']}_List"
            hub_text = (
                f"# {meta['title']}\n\n"
                f"[[Release_Notes|← 返回 Release Notes]]\n\n"
                f"--------------\n\n"
                f"{{{{>toc}}}}\n\n"
                f"## 版本列表\n\n"
                f"{{{{include({list_page})}}}}"
            )
            self.client.put_wiki_page(self.project_id, meta["hub"], hub_text, "产品线索引")

        main = self._build_main(items)
        current = self.client.get_wiki_page(self.project_id, "Release_Notes")
        current_text = (current or {}).get("text", "")
        if not current_text or "{{include(Release_Notes_" not in current_text:
            comment = "启用 include 动态索引模板"
        else:
            comment = "sync main counts"
        self.client.put_wiki_page(self.project_id, "Release_Notes", main, comment)
        return len(items)

    def _refresh_flat(self) -> int:
        items = self._build_items()
        if not items:
            return 0
        tag = proj_tag_from_project(self.project_id, items[0]["page"])
        lines = "\n".join(
            f"- [[{i['page']}|{i['ver']} ({i['date']})]] - {i['summary']}"
            for i in sorted(items, key=lambda x: x["date"], reverse=True)
        )
        text = (
            f"# Release Notes\n\n"
            f"{tag} 固件版本发布记录。固件 bin 存放在 "
            f"[项目文件](/projects/{self.project_id}/files)，Wiki 仅记录变更。\n\n"
            f"--------------\n\n"
            f"{{{{>toc}}}}\n\n"
            f"## 版本列表\n\n"
            f"{lines}"
        )
        self.client.put_wiki_page(self.project_id, "Release_Notes", text, "Release Notes 索引")
        return len(items)

    def _build_main(self, items: list[dict[str, Any]]) -> str:
        tag = proj_tag_from_project(self.project_id, items[0]["page"] if items else None)
        lines = [
            "# Release Notes",
            "",
            f"{tag} 固件发布记录，按产品线分类。固件 bin 在 "
            f"[项目文件](/projects/{self.project_id}/files)，Wiki 仅记录变更。",
            "",
            "> 版本列表由 `{{include(...)}}` 动态嵌入；通过版本发布工具保存后自动同步。",
            "",
            "--------------",
            "",
            "{{>toc}}",
            "",
            "## 产品线索引",
            "",
        ]
        for category, meta in CATEGORY_META.items():
            count = sum(1 for i in items if i["cat"] == category)
            if count:
                lines.append(f"- [[{meta['hub']}|{meta['title']}]] ({count})")
        lines.append("")
        for category, meta in CATEGORY_META.items():
            if not any(i["cat"] == category for i in items):
                continue
            list_page = f"{meta['hub']}_List"
            lines.extend(
                [
                    f"## {meta['title']}",
                    "",
                    f"[[{meta['hub']}|独立页面]]",
                    "",
                    f"{{{{include({list_page})}}}}",
                    "",
                ]
            )
        return "\n".join(lines)

    def _categorize(
        self,
        page_title: str,
        text: str,
        ver: str | None = None,
        commit: str | None = None,
    ) -> str:
        ver = ver or self._extract_version(text, proj_tag_from_project(self.project_id, page_title))
        commit = commit or self._extract_commit(text)
        if "_NP500_FW_" in page_title:
            return "NP500"
        if re.match(r"V5\.4\.7\.", ver, re.I):
            return "Trunking"
        if re.search(r"Record|录音", commit) or (
            re.search(r"录音", text) and not re.match(r"V5\.4", ver, re.I)
        ):
            return "Record"
        return "Regular"

    def _extract_version(self, text: str, tag: str) -> str:
        m = re.search(rf"# Release {re.escape(tag)} (?:NP500 )?FW ([^\r\n]+)", text, re.I)
        if not m:
            m = re.search(r"# Release [A-Za-z0-9]+(?: NP500)? FW ([^\r\n]+)", text, re.I)
        return m.group(1).strip() if m else "?"

    def _extract_date(self, text: str) -> str:
        m = re.search(r"\*\*[^*:]+:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
        return m.group(1) if m else "0000-01-01"

    def _extract_commit(self, text: str) -> str:
        m = re.search(r"\*\*Commit:\*\*\s*([^\r\n]+)", text)
        return m.group(1).strip() if m else ""

    def _extract_summary(self, text: str, ver: str) -> str:
        m = re.search(r"^1\.\s+(.+)$", text, re.M)
        return m.group(1).strip() if m else f"release {ver}"
