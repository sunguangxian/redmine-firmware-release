"""Generic migration from legacy Changelog wiki pages to managed Release pages."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, build_inline_release_block, build_release_markdown, replace_inline_release_block
from .wiki_config import CONFIG_BEGIN, CONFIG_END, CONFIG_PAGE_TITLE, parse_release_wiki_config

DEFAULT_ENTRY_PAGES = ["Changelog"]
VERSION_HEADING_RE = re.compile(
    r"(?m)^(?:h[12]\.\s*|#{1,2}\s*)version\s*:?\s*(?P<version>[^\s(]+)\s*\((?P<date>\d{4}-\d{2}-\d{2})\)"
    r"[^\n]*\r?$",
    re.I,
)
CHANGELOG_TITLE_RE = re.compile(r"(?im)^(?:#|h1\.)\s*Changelog\s+for\s+(?P<model>[^\r\n]+?)\s*$")
SECTION_HEADING_RE = re.compile(r"(?m)^(?:#(?!#)|h1\.)\s*(?P<title>[^\r\n]+?)\s*$")
NON_VERSION_HEADING_RE = re.compile(r"(?im)^(?:#{1,2}|h[12]\.)\s*(?!version\b)[^\r\n]+?\s*$")
ATTACHMENT_RE = re.compile(r"attachment:([^\s;,，；]+)", re.I)


@dataclass
class LegacyAttachmentRef:
    filename: str
    attachment: Optional[Dict[str, Any]] = None


@dataclass
class LegacyRelease:
    model: str
    category_title: str
    source_page: str
    version: str
    date: str
    commit: str
    changelog_items: List[str]
    attachments: List[LegacyAttachmentRef] = field(default_factory=list)
    target_wiki_title: str = ""

    @property
    def version_name(self) -> str:
        return self.version

    @property
    def wiki_title(self) -> str:
        if self.target_wiki_title:
            return self.target_wiki_title
        suffix = self.version.replace(".", "_")
        return f"Release_{self.model}_FW_{suffix}"


@dataclass
class LegacySourcePage:
    title: str
    model: str
    release_count: int
    attachment_ref_count: int
    matched_attachment_count: int


class LegacyChangelogMigrator:
    def __init__(
        self,
        client: RedmineClient,
        project_id: str,
        entry_pages: Optional[List[str]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        release_detail_mode: str = "auto",
    ):
        self.client = client
        self.project_id = project_id
        self.entry_pages = [item.strip() for item in (entry_pages or DEFAULT_ENTRY_PAGES) if item.strip()]
        self._log_callback = log_callback
        self.release_detail_mode = self._normalize_detail_mode(release_detail_mode)
        self._wiki_index: Optional[List[Dict[str, Any]]] = None
        self._pages: Dict[str, Optional[Dict[str, Any]]] = {}

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)

    def _normalize_detail_mode(self, value: str | None) -> str:
        mode = (value or "auto").strip().lower()
        return mode if mode in {"auto", "inline", "page"} else "auto"

    def _selected_detail_mode(self) -> str:
        if self.release_detail_mode in {"inline", "page"}:
            return self.release_detail_mode
        page = self.client.get_wiki_page(self.project_id, CONFIG_PAGE_TITLE)
        if page:
            config = parse_release_wiki_config(page.get("text", ""))
            if config and config.release_detail_mode in {"inline", "page"}:
                return config.release_detail_mode
        return "inline"

    def preview(self) -> Dict[str, Any]:
        releases, sources, warnings = self.scan()
        existing_versions = {item.get("name", ""): item for item in self.client.list_versions(self.project_id)}
        existing_titles = {item.get("title", "") for item in self._get_wiki_index()}
        project_files: List[Dict[str, Any]] = []
        can_read_project_files = True
        try:
            project_files = self.client.list_project_files(self.project_id)
        except RedmineError as exc:
            can_read_project_files = False
            warnings.append(f"无法读取项目文件列表：{exc}。预览无法判断项目文件是否已存在，执行带附件迁移前需要先开通项目文件权限。")

        version_names = {item.version_name for item in releases}
        release_titles = {item.wiki_title for item in releases}
        attachment_refs = [att for item in releases for att in item.attachments]
        matched_refs = [att for att in attachment_refs if att.attachment]
        unmatched_refs = [att for att in attachment_refs if not att.attachment]
        existing_file_keys = self._existing_file_keys(project_files)
        existing_file_count = 0
        upload_count = 0
        for release in releases:
            version = existing_versions.get(release.version_name)
            for att in release.attachments:
                if not att.attachment:
                    continue
                key = (int((version or {}).get("id") or 0), att.filename.lower())
                if can_read_project_files and version and key in existing_file_keys:
                    existing_file_count += 1
                else:
                    upload_count += 1

        problems: List[Dict[str, str]] = []
        duplicate_titles = {title: count for title, count in Counter(item.wiki_title for item in releases).items() if count > 1}
        for title, count in duplicate_titles.items():
            problems.append(
                {
                    "level": "error",
                    "source_page": "",
                    "version": "",
                    "message": f"目标 Release 页面重复 {count} 次：{title}",
                }
            )
        for release in releases:
            for att in release.attachments:
                if not att.attachment:
                    problems.append(
                        {
                            "level": "warning",
                            "source_page": release.source_page,
                            "version": release.version,
                            "message": f"附件未匹配：{att.filename}",
                        }
                    )
        if unmatched_refs:
            warnings.append(f"有 {len(unmatched_refs)} 个附件引用没有匹配到旧 Wiki 附件，执行时会跳过。")
        if duplicate_titles:
            warnings.append("存在重复目标 Release 页面，执行迁移前需要先处理冲突。")

        return {
            "project_id": self.project_id,
            "entry_pages": self.entry_pages,
            "source_page_count": len(sources),
            "model_count": len({item.model for item in releases}),
            "release_count": len(releases),
            "attachment_ref_count": len(attachment_refs),
            "matched_attachment_count": len(matched_refs),
            "versions_to_create": len([name for name in version_names if name not in existing_versions]),
            "existing_versions": len([name for name in version_names if name in existing_versions]),
            "release_pages_to_create": len([title for title in release_titles if title not in existing_titles]),
            "existing_release_pages": len([title for title in release_titles if title in existing_titles]),
            "project_files_to_upload": upload_count,
            "existing_project_files": existing_file_count,
            "can_read_project_files": can_read_project_files,
            "source_pages": [source.__dict__ for source in sources],
            "warnings": warnings,
            "problems": problems,
        }

    def execute(self) -> Dict[str, Any]:
        self._log("开始执行旧项目升级：预览并校验迁移计划")
        preview = self.preview()
        self._log(
            f"预览完成：源页面 {preview.get('source_page_count', 0)} 个，"
            f"历史版本 {preview.get('release_count', 0)} 个，附件引用 {preview.get('attachment_ref_count', 0)} 个"
        )
        blocking = [item for item in preview.get("problems", []) if item.get("level") == "error"]
        if blocking:
            raise RedmineError("迁移预览存在阻塞问题，请先处理重复目标页面或版本。")
        if preview.get("attachment_ref_count") and not preview.get("can_read_project_files"):
            raise RedmineError("当前账号无法读取项目文件列表，不能安全迁移旧附件到项目 Files。请先确认 Redmine 文件模块权限。")
        self._log("重新扫描旧 Wiki 页面，准备写入 Redmine")
        releases, _sources, _warnings = self.scan()
        if not releases:
            self._log("没有可迁移的历史版本，执行结束")
            return {
                "ok": True,
                "preview": preview,
                "created_versions": 0,
                "uploaded_files": 0,
                "updated_release_pages": 0,
                "message": "没有可迁移的历史版本。",
            }

        categories = self._release_categories(releases)
        single_list = len(categories) == 1
        structure = "single_list" if single_list else "multi_list"
        detail_mode = self._selected_detail_mode()
        preview["release_detail_mode"] = detail_mode
        preview["release_detail_mode_label"] = "内联模式" if detail_mode == "inline" else "一版本一页"
        self._log(f"写入 Release_Tool_Config，结构：{structure}，版本模式：{detail_mode}，分类：{', '.join(item['title'] for item in categories)}")
        self._save_release_tool_config(categories, single_list=single_list, detail_mode=detail_mode)
        self._log("创建 Release_Notes 索引结构")
        self._create_release_structure(categories, single_list=single_list, detail_mode=detail_mode)
        self._update_wiki_home_if_needed(releases)
        self._log("读取 Redmine Version 列表")
        versions = {item.get("name", ""): item for item in self.client.list_versions(self.project_id)}
        uploaded_files = 0
        created_versions = 0
        updated_pages = 0

        for idx, release in enumerate(releases, 1):
            self._log(f"处理版本 {idx}/{len(releases)}：{release.version_name}，目标页面 {release.wiki_title}")
            version = versions.get(release.version_name)
            if not version:
                try:
                    self._log(f"创建 Redmine Version：{release.version_name}")
                    version = self.client.create_version(
                        self.project_id,
                        release.version_name,
                        release.date,
                        self._version_description(release),
                    )
                except RedmineError as exc:
                    raise RedmineError(f"创建 Redmine Version 失败：{release.version_name}；{exc}") from exc
                versions[release.version_name] = version
                created_versions += 1
            else:
                self._log(f"复用 Redmine Version：{release.version_name}")

            linked_files: List[Dict[str, Optional[str]]] = []
            try:
                existing_for_version = self._project_files_by_name(int(version["id"]))
            except RedmineError as exc:
                raise RedmineError(f"读取版本文件列表失败：{release.version_name}；{exc}") from exc
            self._log(f"版本 {release.version_name} 已有项目文件 {len(existing_for_version)} 个，待处理附件 {len(release.attachments)} 个")
            for att_idx, att in enumerate(release.attachments, 1):
                if not att.attachment:
                    self._log(f"跳过未匹配附件 {att_idx}/{len(release.attachments)}：{att.filename}")
                    continue
                existing = existing_for_version.get(att.filename.lower())
                if existing:
                    self._log(f"复用项目文件 {att_idx}/{len(release.attachments)}：{att.filename}")
                    linked_files.append(self._linked_file(existing, att.filename))
                    continue

                content_url = att.attachment.get("content_url") or ""
                try:
                    self._log(f"下载旧 Wiki 附件 {att_idx}/{len(release.attachments)}：{att.filename}")
                    content = self.client.download_content_url(content_url)
                    self._log(f"上传附件到 Redmine 临时区：{att.filename}")
                    token = self.client.upload_file(att.filename, content)
                    self._log(f"创建项目文件：{att.filename}")
                    file_obj = self.client.create_project_file(self.project_id, int(version["id"]), att.filename, token)
                    if not self._project_file_url(file_obj, att.filename):
                        file_obj = self._project_files_by_name(int(version["id"])).get(att.filename.lower(), file_obj)
                except RedmineError as exc:
                    raise RedmineError(f"迁移附件失败：版本 {release.version_name}，附件 {att.filename}；{exc}") from exc
                linked_files.append(self._linked_file(file_obj, att.filename))
                uploaded_files += 1

            self._log(f"生成 Release Wiki 内容：{release.wiki_title}")
            form = ReleaseForm(
                project_id=self.project_id,
                proj_tag=release.model,
                version_name=release.version,
                release_date=release.date,
                commit=release.commit,
                product_line=release.category_title or release.model,
                changelog_items=release.changelog_items,
                files=[],
                wiki_title=release.wiki_title,
                replace_attachments=True,
            )
            try:
                if detail_mode == "inline":
                    container = self._legacy_inline_container(release, single_list=single_list)
                    page = self.client.get_wiki_page(self.project_id, container)
                    current = (page or {}).get("text", "")
                    block = build_inline_release_block(
                        form,
                        int(version["id"]),
                        linked_files,
                        source_page=release.source_page,
                        block_id=release.wiki_title,
                        display_version=release.version,
                        container_page=container,
                    )
                    new_text = replace_inline_release_block(current, release.wiki_title, block)
                    self._log(f"写入内联 Release 块：{container} / {release.wiki_title}")
                    self.client.put_wiki_page(self.project_id, container, new_text, "legacy changelog inline migration")
                    self.client.update_version(int(version["id"]), wiki_page_title=container, due_date=release.date, description=self._version_description(release))
                else:
                    text = build_release_markdown(form, int(version["id"]), linked_files)
                    text = text.rstrip() + f"\n\n## 迁移来源\n\n- [[{release.source_page}]]\n"
                    parent_title = "Release_Notes" if single_list else f"Release_Notes_{release.model}"
                    self._log(f"写入 Release Wiki：{release.wiki_title}")
                    self.client.put_wiki_page(
                        self.project_id,
                        release.wiki_title,
                        text,
                        "legacy changelog migration",
                        parent_title=parent_title,
                    )
                    self.client.update_version(int(version["id"]), wiki_page_title=release.wiki_title, due_date=release.date, description=self._version_description(release))
            except RedmineError as exc:
                raise RedmineError(f"写入 Release Wiki 失败：{release.wiki_title}；{exc}") from exc
            updated_pages += 1

        try:
            self._log("重建 Release 索引")
            refreshed = IndexSync(self.client, self.project_id).refresh_all()
        except RedmineError as exc:
            raise RedmineError(f"Release 索引重建失败；{exc}") from exc
        target_word = "处" if detail_mode == "inline" else "页"
        self._log(f"迁移完成：创建版本 {created_versions} 个，上传项目文件 {uploaded_files} 个，更新 Release Wiki {updated_pages} {target_word}")
        return {
            "ok": True,
            "preview": preview,
            "created_versions": created_versions,
            "uploaded_files": uploaded_files,
            "updated_release_pages": updated_pages,
            "refreshed_release_count": refreshed,
            "release_detail_mode": detail_mode,
            "release_detail_mode_label": "内联模式" if detail_mode == "inline" else "一版本一页",
            "message": (
                f"迁移完成：创建版本 {created_versions} 个，上传项目文件 {uploaded_files} 个，"
                f"更新 Release Wiki {updated_pages} {target_word}，重建索引 {refreshed} 个 Release。"
            ),
        }

    def scan(self) -> Tuple[List[LegacyRelease], List[LegacySourcePage], List[str]]:
        warnings: List[str] = []
        source_titles = self._discover_source_titles(warnings)
        releases: List[LegacyRelease] = []
        sources: List[LegacySourcePage] = []

        for title in source_titles:
            page = self._get_page(title, include_attachments=True)
            if not page:
                warnings.append(f"源页面不存在：{title}")
                continue
            text = page.get("text", "") or ""
            model = self._model_for_page(title, text)
            if not model:
                continue
            attachments = self._attachments_by_name(page.get("attachments") or [])
            parsed = self._parse_releases(title, model, text, attachments)
            if not parsed:
                continue
            releases.extend(parsed)
            source_categories = []
            for item in parsed:
                title_value = item.category_title or item.model
                if title_value not in source_categories:
                    source_categories.append(title_value)
            ref_count = sum(len(item.attachments) for item in parsed)
            matched_count = sum(1 for item in parsed for att in item.attachments if att.attachment)
            sources.append(
                LegacySourcePage(
                    title=title,
                    model=", ".join(source_categories),
                    release_count=len(parsed),
                    attachment_ref_count=ref_count,
                    matched_attachment_count=matched_count,
                )
            )

        if not releases:
            warnings.append("没有识别到可迁移的 version 段。")
        self._assign_unique_targets(releases)
        return releases, sources, warnings

    def _assign_unique_targets(self, releases: List[LegacyRelease]) -> None:
        groups: Dict[Tuple[str, str], List[LegacyRelease]] = {}
        for release in releases:
            groups.setdefault((release.model, release.version), []).append(release)

        for (model, version), group in groups.items():
            if len(group) == 1:
                continue
            seen: Dict[str, int] = {}
            for release in group:
                date_key = release.date.replace("-", "")
                base_title = f"Release_{model}_FW_{version.replace('.', '_')}_{date_key}"
                count = seen.get(base_title, 0) + 1
                seen[base_title] = count
                suffix = f"_{count}" if count > 1 else ""
                release.target_wiki_title = f"{base_title}{suffix}"

    def _discover_source_titles(self, warnings: List[str]) -> List[str]:
        titles = [item.get("title", "") for item in self._get_wiki_index() if item.get("title")]
        title_by_key = {title.lower(): title for title in titles}
        selected: List[str] = []
        selected_keys: set[str] = set()
        missing_entries: List[str] = []

        def add_selected(title: str) -> None:
            canonical = title_by_key.get(title.lower(), title)
            key = canonical.lower()
            if key in selected_keys:
                return
            selected_keys.add(key)
            selected.append(canonical)

        for entry in self.entry_pages:
            page = self._get_page(entry)
            if not page:
                missing_entries.append(entry)
                continue
            if self._page_has_versions(page.get("text", "") or ""):
                add_selected(str(page.get("title") or entry))
            for link in re.findall(r"\[\[([^\]|]+)", page.get("text", "") or ""):
                link_title = link.strip()
                if link_title.lower() in title_by_key and link_title.lower() not in {item.lower() for item in self.entry_pages}:
                    add_selected(link_title)

        for title in titles:
            if title.lower() in {item.lower() for item in self.entry_pages}:
                continue
            if self._model_from_title(title):
                add_selected(title)
        if not selected:
            warnings.extend(f"入口页不存在：{entry}" for entry in missing_entries)
        return selected

    def _page_has_versions(self, text: str) -> bool:
        return bool(VERSION_HEADING_RE.search(text or ""))

    def _parse_releases(
        self,
        source_page: str,
        model: str,
        text: str,
        attachments: Dict[str, Dict[str, Any]],
    ) -> List[LegacyRelease]:
        matches = list(VERSION_HEADING_RE.finditer(text))
        result: List[LegacyRelease] = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            section_match = NON_VERSION_HEADING_RE.search(text, start, end)
            if section_match:
                end = section_match.start()
            body = text[start:end].strip()
            attachment_names = self._attachment_names(body)
            category_key, category_title = self._category_for_position(text, match.start(), model)
            result.append(
                LegacyRelease(
                    model=category_key,
                    category_title=category_title,
                    source_page=source_page,
                    version=match.group("version").strip(),
                    date=match.group("date").strip(),
                    commit=self._extract_commit(body),
                    changelog_items=self._extract_changelog_items(body),
                    attachments=[
                        LegacyAttachmentRef(filename=name, attachment=attachments.get(name.lower()))
                        for name in attachment_names
                    ],
                )
            )
        return result

    def _extract_commit(self, body: str) -> str:
        match = re.search(r"commit\s*:\s*(?:commit:)?\s*([^\r\n]+)", body, re.I)
        return match.group(1).strip(" ;；") if match else ""

    def _extract_changelog_items(self, body: str) -> List[str]:
        items: List[str] = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("*") and "commit" in line.lower():
                continue
            if "attachment:" in line.lower():
                continue
            if set(line) <= {"*", "-", "_"}:
                continue
            line = re.sub(r"^(?:[*#-]|\d+[.、])\s*", "", line).strip()
            if line and not line.lower().startswith("commit:"):
                items.append(line)
        return items or ["历史版本迁移"]

    def _attachment_names(self, body: str) -> List[str]:
        result: List[str] = []
        seen = set()
        for match in ATTACHMENT_RE.finditer(body):
            filename = match.group(1).strip()
            key = filename.lower()
            if filename and key not in seen:
                seen.add(key)
                result.append(filename)
        return result

    def _model_from_title(self, title: str) -> str:
        if title.startswith("Changelog_for_"):
            return self._clean_model(title[len("Changelog_for_"):])
        if title.startswith("Changelog_"):
            return self._clean_model(title[len("Changelog_"):])
        if title.startswith("Release_") or title == CONFIG_PAGE_TITLE:
            return ""
        if title in self.entry_pages:
            return ""
        if re.match(r"^[A-Za-z][A-Za-z0-9_+-]*$", title):
            return self._clean_model(title)
        return ""

    def _model_for_page(self, title: str, text: str) -> str:
        match = CHANGELOG_TITLE_RE.search(text or "")
        if match:
            return self._clean_category_key(match.group("model"))
        if title in self.entry_pages and self._page_has_versions(text):
            return self._clean_category_key(self.project_id)
        return self._model_from_title(title)

    def _clean_model(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_+-]+", "_", value.strip()).strip("_")

    def _category_for_position(self, text: str, position: int, default_key: str) -> Tuple[str, str]:
        selected = ""
        for match in SECTION_HEADING_RE.finditer(text or ""):
            if match.start() >= position:
                break
            heading = match.group("title").strip()
            if heading.lower().startswith("version"):
                continue
            selected = heading
        if not selected:
            return default_key, default_key
        if CHANGELOG_TITLE_RE.match(f"# {selected}"):
            key = self._clean_category_key(selected.replace("Changelog for", "", 1))
            return key or default_key, key or default_key
        key = self._clean_category_key(selected)
        return key or default_key, selected

    def _clean_category_key(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^Changelog\s+for\s+", "", text, flags=re.I).strip()
        if "模拟" in text and "信令" in text:
            return "Analog"
        base = re.split(r"[（(]", text, 1)[0].strip()
        cleaned = self._clean_model(base)
        if cleaned:
            return cleaned
        return self._clean_model(text)

    def _attachments_by_name(self, attachments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in attachments:
            filename = item.get("filename") or ""
            if filename:
                result.setdefault(filename.lower(), item)
        return result

    def _release_categories(self, releases: List[LegacyRelease]) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        seen = set()
        for release in releases:
            key = release.model
            if not key or key in seen:
                continue
            seen.add(key)
            result.append({"key": key, "title": release.category_title or key})
        return result

    def _save_release_tool_config(self, categories: List[Dict[str, str]], *, single_list: bool, detail_mode: str = "page") -> None:
        if single_list:
            self._save_single_list_config(categories[0], detail_mode=detail_mode)
        else:
            self._save_multi_list_config(categories, detail_mode=detail_mode)

    def _save_single_list_config(self, category: Dict[str, str], detail_mode: str = "page") -> None:
        lines = [
            "# Release Tool Config",
            "",
            "本页面由旧 Changelog 迁移工具生成，用于配置当前项目的 Release Wiki 管理结构。",
            "",
            CONFIG_BEGIN,
            "```yaml",
            "mode: single_list",
            "main_page: Release_Notes",
            f"release_detail_mode: {detail_mode}",
        ]
        if detail_mode == "page":
            lines.append(f"release_page_prefix: Release_{category['key']}_FW_")
        lines.extend(["```", CONFIG_END, ""])
        self.client.put_wiki_page(
            self.project_id,
            CONFIG_PAGE_TITLE,
            "\n".join(lines),
            "legacy changelog migration config",
        )

    def _save_multi_list_config(self, categories: List[Dict[str, str]], detail_mode: str = "page") -> None:
        lines = [
            "# Release Tool Config",
            "",
            "本页面由旧 Changelog 迁移工具生成，用于配置当前项目的 Release Wiki 管理结构。",
            "",
            CONFIG_BEGIN,
            "```yaml",
            "mode: multi_list",
            "main_page: Release_Notes",
        ]
        lines.append(f"release_detail_mode: {detail_mode}")
        if detail_mode == "page":
            lines.append("release_page_prefix: Release_{category}_FW_")
        lines.append("categories:")
        for category in categories:
            key = category["key"]
            title = category["title"]
            list_page = f"Release_Notes_{key}" if detail_mode == "inline" else f"Release_Notes_{key}_List"
            lines.extend(
                [
                    f"  - key: {key}",
                    f"    title: {title}",
                    f"    hub_page: Release_Notes_{key}",
                    f"    list_page: {list_page}",
                    "",
                ]
            )
        lines.extend(["```", CONFIG_END, ""])
        self.client.put_wiki_page(
            self.project_id,
            CONFIG_PAGE_TITLE,
            "\n".join(lines),
            "legacy changelog migration config",
        )

    def _create_release_structure(self, categories: List[Dict[str, str]], *, single_list: bool, detail_mode: str = "page") -> None:
        if single_list:
            self.client.put_wiki_page(
                self.project_id,
                "Release_Notes",
                self._single_list_placeholder(categories[0]["title"]),
                "legacy changelog migration structure",
            )
            return

        main_lines = [
            "# Release Notes",
            "",
            f"固件 bin 存放在 [项目文件](/projects/{self.project_id}/files)，Wiki 记录版本变更和索引。",
            "",
            "## Product Lines",
            "",
        ]
        for category in categories:
            main_lines.append(f"- [[Release_Notes_{category['key']}|{category['title']}]]")
        self.client.put_wiki_page(
            self.project_id,
            "Release_Notes",
            "\n".join(main_lines).rstrip() + "\n",
            "legacy changelog migration structure",
        )
        for category in categories:
            key = category["key"]
            title = category["title"]
            hub = f"Release_Notes_{key}"
            list_page = f"Release_Notes_{key}" if detail_mode == "inline" else f"Release_Notes_{key}_List"
            if detail_mode == "inline":
                self.client.put_wiki_page(
                    self.project_id,
                    hub,
                    f"# {title}\n\n[[Release_Notes|返回 Release Notes]]\n\n## 版本列表\n\n",
                    "legacy changelog migration structure",
                    parent_title="Release_Notes",
                )
                continue
            self.client.put_wiki_page(
                self.project_id,
                hub,
                (
                    f"# {title}\n\n"
                    "[[Release_Notes|返回 Release Notes]]\n\n"
                    "## Version List\n\n"
                    f"{{{{include({list_page})}}}}\n"
                ),
                "legacy changelog migration structure",
                parent_title="Release_Notes",
            )
            self.client.put_wiki_page(
                self.project_id,
                list_page,
                f"# {title} 版本列表\n\n",
                "legacy changelog migration structure",
                parent_title=hub,
            )

    def _legacy_inline_container(self, release: LegacyRelease, *, single_list: bool) -> str:
        return "Release_Notes" if single_list else f"Release_Notes_{release.model}"

    def _single_list_placeholder(self, model: str) -> str:
        return (
            "# Release Notes\n\n"
            f"{model} 固件版本发布记录。固件 bin 存放在 "
            f"[项目文件](/projects/{self.project_id}/files)，Wiki 记录版本变更。\n\n"
            "## 版本列表\n\n"
            "迁移完成后由工具自动生成。\n"
        )

    def _update_wiki_home_if_needed(self, releases: List[LegacyRelease]) -> None:
        source_titles = sorted({release.source_page for release in releases})
        for title in source_titles:
            if title.startswith("Release_") or title == CONFIG_PAGE_TITLE:
                continue
            page = self._get_page(title, include_attachments=True)
            if not page or not self._page_has_versions(page.get("text", "") or ""):
                continue
            legacy_title = self._legacy_backup_title(title)
            if not self._get_page(legacy_title):
                self.client.put_wiki_page(
                    self.project_id,
                    legacy_title,
                    page.get("text", "") or "",
                    "legacy changelog backup",
                )
                self._log(f"已备份旧 Wiki 页面 {title} 到 {legacy_title}")
            self.client.put_wiki_page(
                self.project_id,
                title,
                (
                    "{{include(Release_Notes)}}\n\n"
                    "## Legacy Changelog\n\n"
                    f"The original Changelog content is preserved at [[{legacy_title}]].\n"
                ),
                "legacy changelog migration home",
            )
            self._log(f"已将旧入口页面 {title} 切换为新的 Release_Notes 入口")

    def _legacy_backup_title(self, title: str) -> str:
        if title == "Wiki":
            return "Legacy_Changelog"
        suffix = self._clean_model(title)
        return f"Legacy_Changelog_{suffix}" if suffix else "Legacy_Changelog"

    def _version_description(self, release: LegacyRelease) -> str:
        first_change = (release.changelog_items[0] if release.changelog_items else "legacy changelog migration").strip()
        lines = [
            f"source: {release.source_page}",
            f"commit: {release.commit}",
            f"summary: {first_change}",
        ]
        return "\n".join(line for line in lines if not line.endswith(": ")).strip()

    def _existing_file_keys(self, project_files: List[Dict[str, Any]]) -> set[Tuple[int, str]]:
        result: set[Tuple[int, str]] = set()
        for item in project_files:
            filename = (item.get("filename") or "").lower()
            version_id = int((item.get("version") or {}).get("id") or 0)
            if filename and version_id:
                result.add((version_id, filename))
        return result

    def _project_files_by_name(self, version_id: int) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in self.client.list_project_files(self.project_id):
            filename = item.get("filename") or ""
            if filename and int((item.get("version") or {}).get("id") or 0) == version_id:
                result.setdefault(filename.lower(), item)
        return result

    def _linked_file(self, file_obj: Dict[str, Any], filename: str) -> Dict[str, Optional[str]]:
        return {
            "filename": filename,
            "description": file_obj.get("description") or "",
            "url": self._project_file_url(file_obj, filename),
        }

    def _project_file_url(self, file_obj: Dict[str, Any], filename: str) -> Optional[str]:
        url = file_obj.get("content_url", "")
        if url and url.startswith("http"):
            return urlparse(url).path
        if url:
            return url
        if file_obj.get("id"):
            return f"/attachments/download/{file_obj['id']}/{filename}"
        return None

    def _get_wiki_index(self) -> List[Dict[str, Any]]:
        if self._wiki_index is None:
            self._wiki_index = self.client.get_wiki_index(self.project_id)
        return self._wiki_index

    def _get_page(self, title: str, *, include_attachments: bool = False) -> Optional[Dict[str, Any]]:
        key = f"{title}|attachments={include_attachments}"
        if key not in self._pages:
            self._pages[key] = self.client.get_wiki_page(
                self.project_id,
                title,
                include_attachments=include_attachments,
            )
        return self._pages[key]
