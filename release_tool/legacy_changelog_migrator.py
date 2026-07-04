"""Generic migration from legacy Changelog wiki pages to managed Release pages."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError
from .release_page import ReleaseForm, build_release_markdown
from .wiki_config import CONFIG_BEGIN, CONFIG_END, CONFIG_PAGE_TITLE

DEFAULT_ENTRY_PAGES = ["Changelog"]
VERSION_HEADING_RE = re.compile(
    r"(?m)^(?:h2\.\s*|##\s*)version\s*:?\s*(?P<version>[^\s(]+)\s*\((?P<date>\d{4}-\d{2}-\d{2})\)"
    r"[^\n]*\r?$",
    re.I,
)
ATTACHMENT_RE = re.compile(r"attachment:([^\s;,，；]+)", re.I)


@dataclass
class LegacyAttachmentRef:
    filename: str
    attachment: Optional[Dict[str, Any]] = None


@dataclass
class LegacyRelease:
    model: str
    source_page: str
    version: str
    date: str
    commit: str
    changelog_items: List[str]
    attachments: List[LegacyAttachmentRef] = field(default_factory=list)
    target_version_name: str = ""
    target_wiki_title: str = ""

    @property
    def version_name(self) -> str:
        return self.target_version_name or f"{self.model} {self.version}"

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
    def __init__(self, client: RedmineClient, project_id: str, entry_pages: Optional[List[str]] = None):
        self.client = client
        self.project_id = project_id
        self.entry_pages = [item.strip() for item in (entry_pages or DEFAULT_ENTRY_PAGES) if item.strip()]
        self._wiki_index: Optional[List[Dict[str, Any]]] = None
        self._pages: Dict[str, Optional[Dict[str, Any]]] = {}

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
            warnings.append(f"无法读取项目文件列表：{exc}。预览将无法判断项目文件是否已存在。")

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
        duplicate_versions = {name: count for name, count in Counter(item.version_name for item in releases).items() if count > 1}
        for title, count in duplicate_titles.items():
            problems.append(
                {
                    "level": "error",
                    "source_page": "",
                    "version": "",
                    "message": f"目标 Release 页面重复 {count} 次：{title}",
                }
            )
        for name, count in duplicate_versions.items():
            problems.append(
                {
                    "level": "error",
                    "source_page": "",
                    "version": "",
                    "message": f"目标 Redmine Version 重复 {count} 次：{name}",
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
        if duplicate_titles or duplicate_versions:
            warnings.append("存在重复目标 Release 页面或 Version，执行迁移前需要先处理冲突。")

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
        preview = self.preview()
        blocking = [item for item in preview.get("problems", []) if item.get("level") == "error"]
        if blocking:
            raise RedmineError("迁移预览存在阻塞问题，请先处理重复目标页面或版本。")
        if preview.get("attachment_ref_count") and not preview.get("can_read_project_files"):
            raise RedmineError("当前账号无法读取项目文件列表，不能安全迁移旧附件到项目 Files。请先确认 Redmine 文件模块权限。")
        releases, _sources, _warnings = self.scan()
        if not releases:
            return {
                "ok": True,
                "preview": preview,
                "created_versions": 0,
                "uploaded_files": 0,
                "updated_release_pages": 0,
                "message": "没有可迁移的历史版本。",
            }

        self._save_release_tool_config(sorted({release.model for release in releases}))
        versions = {item.get("name", ""): item for item in self.client.list_versions(self.project_id)}
        uploaded_files = 0
        created_versions = 0
        updated_pages = 0

        for release in releases:
            version = versions.get(release.version_name)
            if not version:
                version = self.client.create_version(
                    self.project_id,
                    release.version_name,
                    release.date,
                    self._version_description(release),
                )
                versions[release.version_name] = version
                created_versions += 1

            linked_files: List[Dict[str, Optional[str]]] = []
            existing_for_version = self._project_files_by_name(int(version["id"]))
            for att in release.attachments:
                if not att.attachment:
                    continue
                existing = existing_for_version.get(att.filename.lower())
                if existing:
                    linked_files.append(self._linked_file(existing, att.filename))
                    continue

                content_url = att.attachment.get("content_url") or ""
                content = self.client.download_content_url(content_url)
                token = self.client.upload_file(att.filename, content)
                file_obj = self.client.create_project_file(self.project_id, int(version["id"]), att.filename, token)
                if not self._project_file_url(file_obj, att.filename):
                    file_obj = self._project_files_by_name(int(version["id"])).get(att.filename.lower(), file_obj)
                linked_files.append(self._linked_file(file_obj, att.filename))
                uploaded_files += 1

            form = ReleaseForm(
                project_id=self.project_id,
                proj_tag=release.model,
                version_name=release.version,
                release_date=release.date,
                commit=release.commit,
                product_line=release.model,
                changelog_items=release.changelog_items,
                files=[],
                wiki_title=release.wiki_title,
                replace_attachments=True,
            )
            text = build_release_markdown(form, int(version["id"]), linked_files)
            text = text.rstrip() + f"\n\n## 迁移来源\n\n- [[{release.source_page}]]\n"
            self.client.put_wiki_page(
                self.project_id,
                release.wiki_title,
                text,
                "legacy changelog migration",
                parent_title=f"Release_Notes_{release.model}",
            )
            updated_pages += 1

        refreshed = IndexSync(self.client, self.project_id).refresh_all()
        return {
            "ok": True,
            "preview": preview,
            "created_versions": created_versions,
            "uploaded_files": uploaded_files,
            "updated_release_pages": updated_pages,
            "refreshed_release_count": refreshed,
            "message": (
                f"迁移完成：创建版本 {created_versions} 个，上传项目文件 {uploaded_files} 个，"
                f"更新 Release Wiki {updated_pages} 页，重建索引 {refreshed} 个 Release。"
            ),
        }

    def scan(self) -> Tuple[List[LegacyRelease], List[LegacySourcePage], List[str]]:
        warnings: List[str] = []
        source_titles = self._discover_source_titles(warnings)
        releases: List[LegacyRelease] = []
        sources: List[LegacySourcePage] = []

        for title in source_titles:
            model = self._model_from_title(title)
            if not model:
                continue
            page = self._get_page(title, include_attachments=True)
            if not page:
                warnings.append(f"源页面不存在：{title}")
                continue
            text = page.get("text", "") or ""
            attachments = self._attachments_by_name(page.get("attachments") or [])
            parsed = self._parse_releases(title, model, text, attachments)
            if not parsed:
                continue
            releases.extend(parsed)
            ref_count = sum(len(item.attachments) for item in parsed)
            matched_count = sum(1 for item in parsed for att in item.attachments if att.attachment)
            sources.append(
                LegacySourcePage(
                    title=title,
                    model=model,
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
                release.target_version_name = f"{model} {version} {release.date}{f' #{count}' if count > 1 else ''}"

    def _discover_source_titles(self, warnings: List[str]) -> List[str]:
        titles = [item.get("title", "") for item in self._get_wiki_index() if item.get("title")]
        selected: List[str] = []
        for entry in self.entry_pages:
            page = self._get_page(entry)
            if not page:
                warnings.append(f"入口页不存在：{entry}")
                continue
            for link in re.findall(r"\[\[([^\]|]+)", page.get("text", "") or ""):
                link_title = link.strip()
                if link_title in titles and link_title not in selected and link_title not in self.entry_pages:
                    selected.append(link_title)

        for title in titles:
            if title in self.entry_pages:
                continue
            if self._model_from_title(title) and title not in selected:
                selected.append(title)
        return selected

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
            body = text[start:end].strip()
            attachment_names = self._attachment_names(body)
            result.append(
                LegacyRelease(
                    model=model,
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

    def _clean_model(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_+-]+", "_", value.strip()).strip("_")

    def _attachments_by_name(self, attachments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in attachments:
            filename = item.get("filename") or ""
            if filename:
                result.setdefault(filename.lower(), item)
        return result

    def _save_release_tool_config(self, models: List[str]) -> None:
        lines = [
            "# Release Tool Config",
            "",
            "本页面由旧 Changelog 迁移工具生成，用于配置当前项目的 Release Wiki 管理结构。",
            "",
            CONFIG_BEGIN,
            "```yaml",
            "mode: multi_list",
            "main_page: Release_Notes",
            "release_page_prefix: Release_{category}_FW_",
            "categories:",
        ]
        for model in models:
            lines.extend(
                [
                    f"  - key: {model}",
                    f"    title: {model}",
                    f"    hub_page: Release_Notes_{model}",
                    f"    list_page: Release_Notes_{model}_List",
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

    def _version_description(self, release: LegacyRelease) -> str:
        lines = [
            f"model: {release.model}",
            f"commit: {release.commit}",
            f"source: {release.source_page}",
            "",
        ]
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(release.changelog_items, 1))
        return "\n".join(lines).strip()

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
