"""Convert managed Release pages between page and inline detail modes."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .index_sync import CategoryProfile, IndexSync, SYNC_BEGIN, SYNC_END, WikiProfile
from .publisher import ReleasePublisher
from .redmine_api import RELEASE_PAGE_RE, RedmineClient, RedmineError
from .release_page import (
    ReleaseForm,
    build_inline_release_block,
    build_release_markdown,
    parse_inline_ref,
    parse_release_page,
    normalize_inline_release_page,
    replace_inline_release_block,
)
from .wiki_config import CONFIG_BEGIN, CONFIG_END, CONFIG_PAGE_TITLE

VALID_TARGET_MODES = {"inline", "page"}


class ReleaseModeConverter:
    def __init__(self, client: RedmineClient, project_id: str):
        self.client = client
        self.project_id = project_id

    def preview(self, target_mode: str) -> dict[str, Any]:
        target_mode = self._normalize_target_mode(target_mode)
        sync = IndexSync(self.client, self.project_id)
        source = self._source_snapshot(sync, target_mode)
        profile = source["profile"]
        current_mode = source["config_mode"]
        source_mode = source["source_mode"]
        items = source["items"]
        pages_to_write = self._target_pages(sync, profile, items, target_mode)
        pages_to_delete = self._pages_to_delete_after_conversion(profile, items, source_mode, target_mode)
        existing_pages = [title for title in pages_to_write if self.client.get_wiki_page(self.project_id, title)]
        config_will_change = current_mode != target_mode or (
            target_mode == "inline" and self._inline_config_needs_hub_pages(profile)
        )
        warnings: list[str] = list(source["warnings"])
        if source_mode == target_mode:
            warnings.append("当前可识别 Release 内容已经是目标版本模式，执行转换只会切换配置或重建索引。")
        if not items:
            warnings.append("当前模式下没有识别到可转换的 Release 记录。")
        if existing_pages and source_mode != target_mode:
            warnings.append(f"目标模式已有 {len(existing_pages)} 个页面，将用当前 Release 内容刷新这些页面。")
        return {
            "ok": True,
            "project_id": self.project_id,
            "current_mode": current_mode,
            "source_mode": source_mode,
            "target_mode": target_mode,
            "release_count": len(items),
            "pages_to_write": pages_to_write,
            "pages_to_delete": pages_to_delete,
            "existing_pages": existing_pages,
            "config_will_change": config_will_change,
            "warnings": warnings,
            "message": self._message(current_mode, source_mode, target_mode, len(items)),
        }

    def convert(self, target_mode: str) -> dict[str, Any]:
        target_mode = self._normalize_target_mode(target_mode)
        sync = IndexSync(self.client, self.project_id)
        preview = self.preview(target_mode)
        source = self._source_snapshot(sync, target_mode)
        profile = source["profile"]
        current_mode = source["config_mode"]
        source_mode = source["source_mode"]
        items = source["items"]

        converted_count = 0
        deleted_pages: list[str] = []
        if source_mode != target_mode and items:
            if source_mode == "page" and target_mode == "inline":
                converted_count = self._page_to_inline(sync, profile, items)
                deleted_pages = self._delete_page_list_pages(profile, items)
            elif source_mode == "inline" and target_mode == "page":
                converted_count = self._inline_to_page(sync, profile, items)
            else:
                raise RedmineError(f"不支持的 Release 版本模式转换：{source_mode} -> {target_mode}")
        elif source_mode == target_mode == "inline" and items:
            if self._inline_config_needs_hub_pages(profile):
                converted_count = self._inline_list_to_hub(sync, profile, items)
                deleted_pages = self._delete_stale_inline_list_pages(profile, items)
            else:
                converted_count = self._clean_existing_inline_containers(profile, items)
                deleted_pages = self._delete_stale_inline_list_pages(profile, items)

        config_updated = False
        if current_mode != target_mode or (
            target_mode == "inline" and self._inline_config_needs_hub_pages(profile)
        ):
            self._save_config_mode(target_mode)
            config_updated = True

        refreshed_release_count = IndexSync(self.client, self.project_id).refresh_all()
        return {
            **preview,
            "ok": True,
            "converted_count": converted_count,
            "deleted_pages": deleted_pages,
            "config_updated": config_updated,
            "refreshed_release_count": refreshed_release_count,
            "message": (
                f"已完成 {source_mode} -> {target_mode} 转换：复制 Release {converted_count} 个，"
                f"重建索引 {refreshed_release_count} 个；原有内容未删除。"
            ),
        }

    def _clean_existing_inline_containers(self, profile: WikiProfile, items: list[dict[str, Any]]) -> int:
        categories = self._category_map(profile)
        containers: dict[str, CategoryProfile | None] = {}
        for item in items:
            container_page = item.get("container_page") or self._inline_container(
                profile,
                categories.get(item.get("cat") or ""),
            )
            if container_page:
                containers.setdefault(container_page, categories.get(item.get("cat") or ""))

        cleaned = 0
        for container_page, category in containers.items():
            page = self.client.get_wiki_page(self.project_id, container_page)
            if not page:
                continue
            current_text = page.get("text", "")
            new_text = normalize_inline_release_page(self._clean_inline_container_text(current_text, profile, category))
            if new_text != current_text:
                self.client.put_wiki_page(
                    self.project_id,
                    container_page,
                    new_text,
                    "release mode inline cleanup",
                    parent_title=self._inline_parent_title(profile, container_page),
                )
                cleaned += 1
        return cleaned

    def _inline_list_to_hub(self, sync: IndexSync, profile: WikiProfile, items: list[dict[str, Any]]) -> int:
        versions = self._version_ids()
        categories = self._category_map(profile)
        container_texts: dict[str, str] = {}
        source_texts: dict[str, str] = {}
        converted = 0
        for item in items:
            inline_target = parse_inline_ref(item.get("page") or "")
            if not inline_target:
                continue
            source_container, block_id = inline_target
            category = categories.get(item.get("cat") or "")
            target_container = self._inline_conversion_container(profile, category)
            if not target_container:
                continue
            if target_container not in container_texts:
                container = self.client.get_wiki_page(self.project_id, target_container)
                container_texts[target_container] = self._clean_inline_container_text(
                    (container or {}).get("text", ""),
                    profile,
                    category,
                )
            if source_container not in source_texts:
                source = self.client.get_wiki_page(self.project_id, source_container)
                source_texts[source_container] = (source or {}).get("text", "")
            block = self._inline_full_block(source_texts[source_container], block_id)
            if not block:
                continue
            new_text = normalize_inline_release_page(replace_inline_release_block(container_texts[target_container], block_id, block))
            container_texts[target_container] = new_text
            self.client.put_wiki_page(
                self.project_id,
                target_container,
                new_text,
                "release mode inline container migration",
                parent_title=self._inline_conversion_parent_title(profile, target_container, category),
            )
            version_name = item.get("ver") or ""
            if versions.get(version_name):
                self.client.update_version(
                    int(versions[version_name]),
                    wiki_page_title=target_container,
                    due_date=item.get("date") or "",
                )
            converted += 1
        return converted

    def _source_snapshot(self, sync: IndexSync, target_mode: str) -> dict[str, Any]:
        config_profile = sync.discover_profile()
        config_mode = getattr(config_profile, "release_detail_mode", "inline")
        config_items = sync._build_items(config_profile)
        alternate_mode = "page" if config_mode == "inline" else "inline"
        alternate_profile = replace(config_profile, release_detail_mode=alternate_mode)
        alternate_items = sync._build_items(alternate_profile)

        source_profile = config_profile
        source_mode = config_mode
        source_items = config_items
        warnings: list[str] = []

        if config_mode == target_mode and not config_items and alternate_items:
            source_profile = alternate_profile
            source_mode = alternate_mode
            source_items = alternate_items
            warnings.append(
                f"Release_Tool_Config 当前是 {config_mode}，但该模式未识别到 Release；"
                f"已从现有 {alternate_mode} 内容识别到 {len(alternate_items)} 个 Release，将按实际内容转换。"
            )
        elif config_mode != target_mode and not config_items and alternate_items:
            source_profile = alternate_profile
            source_mode = alternate_mode
            source_items = alternate_items
            warnings.append(
                f"Release_Tool_Config 当前是 {config_mode}，但该模式未识别到 Release；"
                f"已改用现有 {alternate_mode} 内容作为源。"
            )

        return {
            "profile": source_profile,
            "config_mode": config_mode,
            "source_mode": source_mode,
            "items": source_items,
            "warnings": warnings,
        }

    def _page_to_inline(self, sync: IndexSync, profile: WikiProfile, items: list[dict[str, Any]]) -> int:
        versions = self._version_ids()
        categories = self._category_map(profile)
        container_texts: dict[str, str] = {}
        converted = 0
        for item in items:
            title = item.get("page") or ""
            page = self.client.get_wiki_page(self.project_id, title)
            if not page:
                continue
            text = page.get("text", "")
            parsed = parse_release_page(title, text)
            version_name = parsed.get("version_name") or item.get("ver") or ""
            category = categories.get(item.get("cat") or "")
            container_page = self._inline_conversion_container(profile, category)
            form = self._form_from_parsed(parsed, version_name, title, category)
            block = build_inline_release_block(
                form,
                versions.get(version_name),
                parsed.get("files") or [],
                source_page=title,
                block_id=title,
                display_version=version_name,
                container_page=container_page,
            )
            if container_page not in container_texts:
                container = self.client.get_wiki_page(self.project_id, container_page)
                container_texts[container_page] = self._clean_inline_container_text(
                    (container or {}).get("text", ""),
                    profile,
                    category,
                )
            current_text = container_texts[container_page]
            new_text = replace_inline_release_block(current_text, title, block)
            container_texts[container_page] = new_text
            self.client.put_wiki_page(
                self.project_id,
                container_page,
                new_text,
                "release mode conversion to inline",
                parent_title=self._inline_conversion_parent_title(profile, container_page, category),
            )
            if versions.get(version_name):
                self.client.update_version(
                    int(versions[version_name]),
                    wiki_page_title=container_page,
                    due_date=parsed.get("release_date") or "",
                )
            converted += 1
        return converted

    def _clean_inline_container_text(
        self,
        text: str,
        profile: WikiProfile,
        category: CategoryProfile | None,
    ) -> str:
        title = category.title if category else "Release Notes"
        current = text or f"# {title}\n\n{{{{>toc}}}}\n"
        inline_match = re.search(r"<!-- RELEASE_INLINE_BEGIN:", current)
        prefix = current[: inline_match.start()] if inline_match else current
        suffix = current[inline_match.start() :] if inline_match else ""
        prefix = re.sub(rf"{re.escape(SYNC_BEGIN)}.*?{re.escape(SYNC_END)}", "", prefix, flags=re.S)
        prefix = re.sub(rf"(?m)^\s*\[\[{re.escape(profile.main_page)}\|[^\]]*Release Notes[^\]]*\]\]\s*$", "", prefix)
        prefix = re.sub(r"(?m)^\s*#{2,6}\s+版本列表\s*$", "", prefix)
        prefix = re.sub(r"(?im)^\s*#{2,6}\s+Version\s+List\s*$", "", prefix)
        prefix = re.sub(r"(?m)^\s*\{\{include\([^)]*_List\)\}\}\s*$", "", prefix)
        prefix = re.sub(r"(?m)^\s*-+\s*$", "", prefix)
        prefix = re.sub(r"(?m)^\s*-\s+\[\[Release_[^\]|]*_FW_[^\]]*(?:\|[^\]]*)?\]\].*$", "", prefix)
        prefix = re.sub(r"\n{3,}", "\n\n", prefix).strip()
        prefix = self._dedupe_toc(prefix)
        if not prefix:
            prefix = f"# {title}"
        if "{{>toc}}" not in prefix:
            heading = re.match(r"(?P<head>\s*#\s+[^\r\n]+)(?P<rest>.*)", prefix, re.S)
            if heading:
                prefix = f"{heading.group('head')}\n\n{{{{>toc}}}}\n{heading.group('rest').lstrip()}"
            else:
                prefix = f"{{{{>toc}}}}\n\n{prefix}"
        return (prefix.rstrip() + "\n\n" + suffix.lstrip()).rstrip() + "\n"

    def _dedupe_toc(self, text: str) -> str:
        seen = False

        def repl(match: re.Match[str]) -> str:
            nonlocal seen
            if seen:
                return ""
            seen = True
            return match.group(0).strip()

        return re.sub(r"(?m)^\s*\{\{>toc\}\}\s*$", repl, text or "")

    def _inline_to_page(self, sync: IndexSync, profile: WikiProfile, items: list[dict[str, Any]]) -> int:
        versions = self._version_ids()
        categories = self._category_map(profile)
        converted = 0
        for item in items:
            source_title = item.get("page") or ""
            inline_target = parse_inline_ref(source_title)
            if not inline_target:
                continue
            category = categories.get(item.get("cat") or "")
            parsed = parse_release_page(source_title, item.get("text") or self._inline_block_text(inline_target))
            version_name = parsed.get("version_name") or item.get("ver") or ""
            form = self._form_from_parsed(parsed, version_name, "", category)
            title = self._page_title_for_inline(sync, profile, form, inline_target[1])
            form.wiki_title = title
            markdown = build_release_markdown(
                form,
                versions.get(version_name),
                parsed.get("files") or [],
                main_page=profile.main_page,
            )
            self.client.put_wiki_page(
                self.project_id,
                title,
                markdown,
                "release mode conversion to page",
                parent_title=self._page_parent_title(profile, category),
            )
            if versions.get(version_name):
                self.client.update_version(
                    int(versions[version_name]),
                    wiki_page_title=title,
                    due_date=parsed.get("release_date") or "",
                )
            converted += 1
        return converted

    def _target_pages(
        self,
        sync: IndexSync,
        profile: WikiProfile,
        items: list[dict[str, Any]],
        target_mode: str,
    ) -> list[str]:
        categories = self._category_map(profile)
        result: list[str] = []
        if target_mode == "inline":
            for item in items:
                page = self._inline_conversion_container(profile, categories.get(item.get("cat") or ""))
                if page and page not in result:
                    result.append(page)
            return result

        for item in items:
            source_title = item.get("page") or ""
            inline_target = parse_inline_ref(source_title)
            category = categories.get(item.get("cat") or "")
            parsed = parse_release_page(source_title, item.get("text") or "")
            version_name = parsed.get("version_name") or item.get("ver") or ""
            form = self._form_from_parsed(parsed, version_name, "", category)
            title = self._page_title_for_inline(sync, profile, form, inline_target[1] if inline_target else "")
            if title and title not in result:
                result.append(title)
        return result

    def _pages_to_delete_after_conversion(
        self,
        profile: WikiProfile,
        items: list[dict[str, Any]],
        source_mode: str,
        target_mode: str,
    ) -> list[str]:
        if target_mode != "inline":
            return []
        result: list[str] = []
        if source_mode == "page":
            if profile.mode == "multi_list":
                categories = self._category_map(profile)
                for item in items:
                    category = categories.get(item.get("cat") or "")
                    if category and category.list_page != category.hub and category.list_page not in result:
                        result.append(category.list_page)
            for item in items:
                self._append_release_detail_page(result, item.get("page") or "")
        elif source_mode == "inline":
            if profile.mode == "multi_list":
                result.extend(self._stale_inline_list_page_titles(profile, items))
            for item in items:
                self._append_release_detail_page(result, item.get("block_id") or "")
        return result

    def _stale_inline_list_page_titles(self, profile: WikiProfile, items: list[dict[str, Any]]) -> list[str]:
        result: list[str] = []
        for category in profile.categories:
            if category.list_page != category.hub:
                if category.list_page not in result:
                    result.append(category.list_page)
                continue
            stale_title = f"{category.hub}_List"
            if stale_title == category.hub or stale_title in result:
                continue
            stale_page = self.client.get_wiki_page(self.project_id, stale_title)
            if not stale_page:
                continue
            hub_page = self.client.get_wiki_page(self.project_id, category.hub)
            stale_text = (stale_page or {}).get("text", "")
            hub_text = (hub_page or {}).get("text", "")
            if "RELEASE_INLINE_BEGIN:" in stale_text and "RELEASE_INLINE_BEGIN:" not in hub_text:
                continue
            if any(item.get("cat") == category.key for item in items):
                result.append(stale_title)
        return result

    def _delete_page_list_pages(self, profile: WikiProfile, items: list[dict[str, Any]]) -> list[str]:
        deleted: list[str] = []
        for title in self._pages_to_delete_after_conversion(profile, items, "page", "inline"):
            if not self.client.get_wiki_page(self.project_id, title):
                continue
            self.client.delete_wiki_page(self.project_id, title)
            deleted.append(title)
        return deleted

    def _delete_stale_inline_list_pages(self, profile: WikiProfile, items: list[dict[str, Any]]) -> list[str]:
        deleted: list[str] = []
        for stale_title in self._pages_to_delete_after_conversion(profile, items, "inline", "inline"):
            self.client.delete_wiki_page(self.project_id, stale_title)
            deleted.append(stale_title)
        return deleted

    def _append_release_detail_page(self, result: list[str], title: str) -> None:
        if self._is_release_detail_page(title) and title not in result:
            result.append(title)

    def _is_release_detail_page(self, title: str) -> bool:
        return bool(title and RELEASE_PAGE_RE.match(title) and self.client.get_wiki_page(self.project_id, title))

    def _form_from_parsed(
        self,
        parsed: dict[str, Any],
        version_name: str,
        wiki_title: str,
        category: CategoryProfile | None,
    ) -> ReleaseForm:
        changelog = [line.strip() for line in (parsed.get("changelog") or "").splitlines() if line.strip()]
        return ReleaseForm(
            project_id=self.project_id,
            proj_tag=self.project_id.upper(),
            version_name=version_name,
            release_date=parsed.get("release_date") or "",
            commit=parsed.get("commit") or "",
            product_line=(category.title if category else parsed.get("product_line") or ""),
            changelog_items=changelog,
            wiki_title=wiki_title or None,
        )

    def _page_title_for_inline(self, sync: IndexSync, profile: WikiProfile, form: ReleaseForm, block_id: str) -> str:
        if block_id.startswith("Release_") and "_FW_" in block_id:
            return block_id
        configured = ReleasePublisher(self.client)._configured_release_title(form, sync, profile)
        return configured or form.computed_title

    def _inline_block_text(self, inline_target: tuple[str, str]) -> str:
        container_page, block_id = inline_target
        page = self.client.get_wiki_page(self.project_id, container_page)
        text = (page or {}).get("text", "")
        pattern = re.compile(
            rf"<!-- RELEASE_INLINE_BEGIN:{re.escape(block_id)}\s*-->(.*?)<!-- RELEASE_INLINE_END:{re.escape(block_id)}\s*-->",
            re.S,
        )
        match = pattern.search(text)
        return match.group(1).strip() if match else ""

    def _inline_full_block(self, page_text: str, block_id: str) -> str:
        pattern = re.compile(
            rf"<!-- RELEASE_INLINE_BEGIN:{re.escape(block_id)}\s*-->.*?<!-- RELEASE_INLINE_END:{re.escape(block_id)}\s*-->",
            re.S,
        )
        match = pattern.search(page_text or "")
        return match.group(0).strip() if match else ""

    def _inline_container(self, profile: WikiProfile, category: CategoryProfile | None) -> str:
        if profile.mode == "multi_list" and category:
            return category.list_page
        return profile.main_page

    def _inline_conversion_container(self, profile: WikiProfile, category: CategoryProfile | None) -> str:
        if profile.mode == "multi_list" and category:
            return category.hub
        return profile.main_page

    def _inline_conversion_parent_title(
        self,
        profile: WikiProfile,
        container_page: str,
        category: CategoryProfile | None,
    ) -> str | None:
        if profile.mode != "multi_list":
            return None
        if category and container_page == category.hub:
            return profile.main_page
        return self._inline_parent_title(profile, container_page)

    def _inline_parent_title(self, profile: WikiProfile, container_page: str) -> str | None:
        if profile.mode != "multi_list":
            return None
        for category in profile.categories:
            if category.list_page == container_page:
                return category.hub if category.list_page != category.hub else profile.main_page
        return None

    def _page_parent_title(self, profile: WikiProfile, category: CategoryProfile | None) -> str | None:
        if profile.mode != "multi_list":
            return profile.main_page
        return category.hub if category else profile.main_page

    def _version_ids(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.client.list_versions(self.project_id):
            name = (item.get("name") or "").strip()
            if name and item.get("id"):
                result[name] = int(item["id"])
        return result

    def _category_map(self, profile: WikiProfile) -> dict[str, CategoryProfile]:
        return {category.key: category for category in profile.categories}

    def _inline_config_needs_hub_pages(self, profile: WikiProfile) -> bool:
        return profile.mode == "multi_list" and any(category.list_page != category.hub for category in profile.categories)

    def _save_config_mode(self, target_mode: str) -> None:
        page = self.client.get_wiki_page(self.project_id, CONFIG_PAGE_TITLE)
        if not page:
            raise RedmineError(f"未找到 {CONFIG_PAGE_TITLE}，无法切换 Release 版本模式。")
        text = self._replace_config_mode(page.get("text", ""), target_mode)
        self.client.put_wiki_page(self.project_id, CONFIG_PAGE_TITLE, text, "release detail mode conversion")

    def _replace_config_mode(self, text: str, target_mode: str) -> str:
        block_pattern = re.compile(rf"{re.escape(CONFIG_BEGIN)}(?P<body>.*?){re.escape(CONFIG_END)}", re.S)

        def update_body(body: str) -> str:
            mode_pattern = re.compile(r"(?m)^(?P<prefix>\s*release_detail_mode\s*:\s*).*$")
            if mode_pattern.search(body):
                body = mode_pattern.sub(lambda m: f"{m.group('prefix')}{target_mode}", body, count=1)
                return self._inline_config_uses_hub_pages(body) if target_mode == "inline" else body
            main_pattern = re.compile(r"(?m)^(\s*main_page\s*:\s*.*)$")
            if main_pattern.search(body):
                body = main_pattern.sub(lambda m: f"{m.group(1)}\nrelease_detail_mode: {target_mode}", body, count=1)
                return self._inline_config_uses_hub_pages(body) if target_mode == "inline" else body
            body = body.rstrip() + f"\nrelease_detail_mode: {target_mode}\n"
            return self._inline_config_uses_hub_pages(body) if target_mode == "inline" else body

        match = block_pattern.search(text or "")
        if match:
            new_body = update_body(match.group("body"))
            return text[: match.start("body")] + new_body + text[match.end("body") :]
        return update_body(text or "")

    def _inline_config_uses_hub_pages(self, body: str) -> str:
        lines = body.splitlines()
        result: list[str] = []
        current_hub = ""
        for line in lines:
            hub_match = re.match(r"^(\s*hub_page\s*:\s*)(\S+)\s*$", line)
            if hub_match:
                current_hub = hub_match.group(2).strip()
                result.append(line)
                continue
            list_match = re.match(r"^(\s*list_page\s*:\s*)\S+\s*$", line)
            if list_match and current_hub:
                result.append(f"{list_match.group(1)}{current_hub}")
                continue
            result.append(line)
        return "\n".join(result)

    def _normalize_target_mode(self, target_mode: str) -> str:
        target_mode = (target_mode or "").strip().lower()
        if target_mode not in VALID_TARGET_MODES:
            raise RedmineError("目标版本模式必须是 inline 或 page。")
        return target_mode

    def _message(self, current_mode: str, source_mode: str, target_mode: str, count: int) -> str:
        if source_mode == target_mode:
            return f"当前可识别内容已经是 {target_mode} 模式，可重建索引确认状态；识别 Release {count} 个。"
        if current_mode != source_mode:
            return f"配置为 {current_mode}，实际按 {source_mode} 识别；准备执行 {source_mode} -> {target_mode} 转换，识别 Release {count} 个。"
        return f"准备执行 {source_mode} -> {target_mode} 转换；识别 Release {count} 个。"
