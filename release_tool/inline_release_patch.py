"""内联版本发布模式补丁。

该模块让 Release_Tool_Config 中的 release_detail_mode=inline 生效。
保留 page 模式的原有行为不变。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .index_sync import IndexSync
from .legacy_changelog_migrator import LegacyChangelogMigrator
from .publisher import ReleasePublisher
from .redmine_api import RedmineError
from .release_page import (
    ReleaseForm,
    build_inline_release_block,
    build_release_markdown,
    delete_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    merge_release_files,
    parse_inline_ref,
    parse_inline_releases,
    parse_release_files,
    parse_release_page,
    replace_inline_release_block,
)
from .release_structure_guard import ensure_release_structure_ready
from .wiki_config import CONFIG_BEGIN, CONFIG_END, CONFIG_PAGE_TITLE, parse_release_wiki_config


_PATCHED = False
_ORIGINALS: dict[str, Any] = {}


def is_inline_profile(profile: Any) -> bool:
    return getattr(profile, "release_detail_mode", "inline") == "inline"


def normalize_migration_detail_mode(value: str | None) -> str:
    mode = (value or "auto").strip().lower()
    return mode if mode in {"auto", "inline", "page"} else "auto"


def selected_migration_detail_mode(migrator: LegacyChangelogMigrator) -> str:
    selected = normalize_migration_detail_mode(getattr(migrator, "release_detail_mode", "auto"))
    if selected in {"inline", "page"}:
        return selected
    page = migrator.client.get_wiki_page(migrator.project_id, CONFIG_PAGE_TITLE)
    if page:
        config = parse_release_wiki_config(page.get("text", ""))
        if config and config.release_detail_mode in {"inline", "page"}:
            return config.release_detail_mode
    return "inline"


def apply_inline_release_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    _ORIGINALS["index_discover_profile"] = IndexSync.discover_profile
    _ORIGINALS["index_build_items"] = IndexSync._build_items
    _ORIGINALS["index_sync_after_publish"] = IndexSync.sync_after_publish
    _ORIGINALS["index_refresh_all"] = IndexSync.refresh_all
    _ORIGINALS["index_format_release_lines"] = IndexSync._format_release_lines
    _ORIGINALS["publisher_publish_locked"] = ReleasePublisher._publish_locked
    _ORIGINALS["publisher_list_releases"] = ReleasePublisher.list_releases
    _ORIGINALS["legacy_execute"] = LegacyChangelogMigrator.execute

    IndexSync.discover_profile = _discover_profile_with_detail_mode  # type: ignore[method-assign]
    IndexSync._build_items = _build_items_inline_aware  # type: ignore[method-assign]
    IndexSync.sync_after_publish = _sync_after_publish_inline_aware  # type: ignore[method-assign]
    IndexSync.refresh_all = _refresh_all_inline_aware  # type: ignore[method-assign]
    IndexSync._format_release_lines = _format_release_lines_inline_aware  # type: ignore[method-assign]
    IndexSync.inline_container_for_release = _inline_container_for_release  # type: ignore[attr-defined]
    ReleasePublisher._publish_locked = _publish_locked_inline_aware  # type: ignore[method-assign]
    ReleasePublisher.list_releases = _list_releases_inline_aware  # type: ignore[method-assign]
    LegacyChangelogMigrator.execute = _execute_legacy_inline_aware  # type: ignore[method-assign]


def _discover_profile_with_detail_mode(self: IndexSync):
    profile = _ORIGINALS["index_discover_profile"](self)
    try:
        page = self._get_page(CONFIG_PAGE_TITLE)
        config = parse_release_wiki_config((page or {}).get("text", ""))
        detail_mode = (config.release_detail_mode if config else "inline") or "inline"
    except Exception:
        detail_mode = "inline"
    setattr(profile, "release_detail_mode", detail_mode)
    return profile


def _build_items_inline_aware(self: IndexSync, profile):
    if not is_inline_profile(profile):
        return _ORIGINALS["index_build_items"](self, profile)

    result: list[dict[str, Any]] = []
    if profile.mode == "multi_list":
        containers = [(category.key, category.list_page) for category in profile.categories]
    else:
        containers = [("", profile.main_page)]

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


def _format_release_lines_inline_aware(self: IndexSync, items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- [[{item.get('container_page') or item['page']}|{item['ver']} ({item['date']})]] - {item['summary']}"
        for item in items
    )


def _sync_after_publish_inline_aware(self: IndexSync, page_title: str, page_text: str) -> None:
    self._page_cache[page_title] = {"title": page_title, "text": page_text}
    profile = self.discover_profile()
    if not is_inline_profile(profile):
        return _ORIGINALS["index_sync_after_publish"](self, page_title, page_text)

    if profile.mode == "multi_list":
        items = self._build_items(profile)
        main = self._build_main(profile, items)
        self.client.put_wiki_page(self.project_id, profile.main_page, main, comment="auto sync main counts")
        self._page_cache[profile.main_page] = {"title": profile.main_page, "text": main}


def _refresh_all_inline_aware(self: IndexSync) -> int:
    profile = self.discover_profile()
    if not is_inline_profile(profile):
        return _ORIGINALS["index_refresh_all"](self)

    items = self._build_items(profile)
    if profile.mode == "multi_list" and items:
        main = self._build_main(profile, items)
        self.client.put_wiki_page(self.project_id, profile.main_page, main, comment="auto sync main counts")
        self._page_cache[profile.main_page] = {"title": profile.main_page, "text": main}
    return len(items)


def _inline_container_for_release(self: IndexSync, profile: Any, page_title: str, page_text: str) -> str:
    if profile.mode != "multi_list":
        return profile.main_page
    category = self._categorize(page_title, page_text, categories=profile.categories)
    for item in profile.categories:
        if item.key == category:
            return item.list_page
    raise RedmineError("无法按当前分类配置确定内联版本应写入哪个列表页。")


def _inline_display_version(block_id: str, block: str) -> str:
    if not block:
        return ""
    try:
        parsed = parse_release_page(inline_ref("_", block_id), block)
        return str(parsed.get("version_name") or "").strip()
    except Exception:
        return ""


def _next_block_id(old_block_id: str, old_display_version: str, new_display_version: str, is_edit: bool) -> str:
    new_display_version = (new_display_version or "").strip()
    if not is_edit:
        return new_display_version
    old_block_id = (old_block_id or "").strip()
    old_display_version = (old_display_version or "").strip()
    # 旧迁移会用唯一 Release 标题作为 block_id；这种情况下编辑时保留 block_id，避免重复版本再次冲突。
    if old_block_id and old_display_version and old_block_id != old_display_version:
        return old_block_id
    return new_display_version


def _publish_locked_inline_aware(
    self: ReleasePublisher,
    form: ReleaseForm,
    logs: list[str] | None = None,
    progress=None,
) -> str:
    index_sync, profile = ensure_release_structure_ready(self.client, form.project_id, logs)
    if not is_inline_profile(profile):
        return _ORIGINALS["publisher_publish_locked"](self, form, logs, progress)

    try:
        self._progress(progress, "release", "running")
        self._log(logs, f"项目发布结构：{profile.mode}，内联版本")
        self._validate_category(form, index_sync, profile, logs)
        version_name = self._configured_version_name(form, index_sync, profile)
        version = self._get_or_create_version(form, logs, version_name=version_name)
        self._progress(progress, "release", "success")
    except Exception:
        self._progress(progress, "release", "failed")
        raise

    old_block_id = form.version_name.strip()
    is_edit = False
    inline_target = parse_inline_ref(form.wiki_title)
    if inline_target:
        container_page, old_block_id = inline_target
        form.wiki_title = None
        is_edit = True
    else:
        container_page = index_sync.inline_container_for_release(
            profile,
            form.page_title,
            f"**产品线:** {form.product_line}\n**Commit:** {form.commit}\n",
        )

    try:
        self._progress(progress, "wiki", "running")
        page = self.client.get_wiki_page(form.project_id, container_page)
        current_text = (page or {}).get("text", "")
        old_block = extract_inline_release_block(current_text, old_block_id)
        old_display_version = _inline_display_version(old_block_id, old_block)
        new_block_id = _next_block_id(old_block_id, old_display_version, form.version_name, is_edit)
        if is_edit and old_block_id != new_block_id:
            self._log(logs, f"内联编辑目标块：{old_block_id} -> {new_block_id}")
        elif is_edit and old_block_id != form.version_name.strip():
            self._log(logs, f"内联编辑保留唯一块标识：{old_block_id}，显示版本：{form.version_name.strip()}")
        old_files = parse_release_files(old_block) if old_block else []
        self._log(logs, f"内联版本页面：{container_page}，已有附件 {len(old_files)} 个")
    except Exception:
        self._progress(progress, "wiki", "failed")
        raise

    try:
        if form.files:
            self._progress(progress, "file", "running")
        else:
            self._progress(progress, "file", "skipped")
        new_files = self._upload_files(form, version["id"], logs)
        linked_files = merge_release_files(old_files, new_files, replace=form.replace_attachments)
        self._log(logs, f"附件列表合并完成：最终 {len(linked_files)} 个")
        if form.files:
            self._progress(progress, "file", "success")
    except Exception:
        self._progress(progress, "file", "failed")
        raise

    try:
        base_text = current_text
        if old_block_id and old_block_id != new_block_id:
            base_text = delete_inline_release_block(base_text, old_block_id)
            self._log(logs, f"已删除旧内联版本块：{old_block_id}")
        block = build_inline_release_block(form, int(version["id"]), linked_files, block_id=new_block_id)
        new_text = replace_inline_release_block(base_text, new_block_id, block)
        parent_title = _inline_parent_title(profile, container_page)
        self.client.put_wiki_page(
            form.project_id,
            container_page,
            new_text,
            "release tool inline update",
            parent_title=parent_title,
        )
        self._log(logs, f"内联版本写入完成：{container_page} / {form.version_name}")
        self._progress(progress, "wiki", "success")
    except Exception:
        self._progress(progress, "wiki", "failed")
        raise

    try:
        self._progress(progress, "release", "running")
        self.client.update_version(
            version["id"],
            wiki_page_title=container_page,
            due_date=form.release_date,
            description=self._version_description(form),
        )
        self._progress(progress, "release", "success")
    except Exception:
        self._progress(progress, "release", "failed")
        raise

    try:
        self._progress(progress, "index", "running")
        index_sync.sync_after_publish(container_page, new_text)
        self._log(logs, "内联版本索引同步完成")
        self._progress(progress, "index", "success")
    except Exception:
        self._progress(progress, "index", "failed")
        raise

    return inline_ref(container_page, new_block_id)


def _inline_parent_title(profile: Any, container_page: str) -> str | None:
    if profile.mode != "multi_list":
        return None
    for category in profile.categories:
        if category.list_page == container_page:
            return category.hub if category.list_page != category.hub else profile.main_page
    return None


def _list_releases_inline_aware(self: ReleasePublisher, project_id: str) -> list[dict]:
    sync = IndexSync(self.client, project_id)
    try:
        profile = sync.discover_profile()
    except RedmineError:
        return _ORIGINALS["publisher_list_releases"](self, project_id)
    if not is_inline_profile(profile):
        return _ORIGINALS["publisher_list_releases"](self, project_id)

    rows = []
    for item in sync._build_items(profile):
        rows.append(
            {
                "title": item["page"],
                "version": item["ver"],
                "date": item["date"],
                "product_line": item.get("product_line", ""),
                "summary": item.get("summary", ""),
            }
        )
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


def _execute_legacy_inline_aware(self: LegacyChangelogMigrator) -> Dict[str, Any]:
    self._log("开始执行旧项目升级：预览并校验迁移计划")
    preview = self.preview()
    blocking = [item for item in preview.get("problems", []) if item.get("level") == "error"]
    if blocking:
        raise RedmineError("迁移预览存在阻塞问题，请先处理重复目标页面或版本。")
    if preview.get("attachment_ref_count") and not preview.get("can_read_project_files"):
        raise RedmineError("当前账号无法读取项目文件列表，不能安全迁移旧附件到项目 Files。请先确认 Redmine 文件模块权限。")

    releases, _sources, _warnings = self.scan()
    if not releases:
        return {"ok": True, "preview": preview, "created_versions": 0, "uploaded_files": 0, "updated_release_pages": 0, "message": "没有可迁移的历史版本。"}

    categories = self._release_categories(releases)
    single_list = len(categories) == 1
    detail_mode = selected_migration_detail_mode(self)
    preview["release_detail_mode"] = detail_mode
    preview["release_detail_mode_label"] = _detail_mode_label(detail_mode)
    self._log(f"写入 Release_Tool_Config，结构：{'single_list' if single_list else 'multi_list'}，版本模式：{detail_mode}")
    _save_legacy_config(self, categories, single_list=single_list, detail_mode=detail_mode)
    _create_legacy_structure(self, categories, single_list=single_list, detail_mode=detail_mode)
    self._update_wiki_home_if_needed(releases)

    versions = {item.get("name", ""): item for item in self.client.list_versions(self.project_id)}
    uploaded_files = 0
    created_versions = 0
    updated_pages = 0

    for idx, release in enumerate(releases, 1):
        self._log(f"处理版本 {idx}/{len(releases)}：{release.version_name}")
        version = versions.get(release.version_name)
        if not version:
            version = self.client.create_version(self.project_id, release.version_name, release.date, self._version_description(release))
            versions[release.version_name] = version
            created_versions += 1

        existing_for_version = self._project_files_by_name(int(version["id"]))
        linked_files: List[Dict[str, Optional[str]]] = []
        for att in release.attachments:
            if not att.attachment:
                continue
            existing = existing_for_version.get(att.filename.lower())
            if existing:
                linked_files.append(self._linked_file(existing, att.filename))
                continue
            content = self.client.download_content_url(att.attachment.get("content_url") or "")
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
            product_line=release.category_title or release.model,
            changelog_items=release.changelog_items,
            files=[],
            wiki_title=release.wiki_title,
            replace_attachments=True,
        )

        if detail_mode == "inline":
            container = _legacy_inline_container(release, single_list=single_list)
            page = self.client.get_wiki_page(self.project_id, container)
            current = (page or {}).get("text", "")
            block_id = release.wiki_title
            block = build_inline_release_block(
                form,
                int(version["id"]),
                linked_files,
                source_page=release.source_page,
                block_id=block_id,
                display_version=release.version,
            )
            new_text = replace_inline_release_block(current, block_id, block)
            self.client.put_wiki_page(self.project_id, container, new_text, "legacy changelog inline migration")
            self.client.update_version(int(version["id"]), wiki_page_title=container, due_date=release.date, description=self._version_description(release))
        else:
            text = build_release_markdown(form, int(version["id"]), linked_files)
            text = text.rstrip() + f"\n\n## 迁移来源\n\n- [[{release.source_page}]]\n"
            parent_title = "Release_Notes" if single_list else f"Release_Notes_{release.model}"
            self.client.put_wiki_page(self.project_id, release.wiki_title, text, "legacy changelog migration", parent_title=parent_title)
            self.client.update_version(int(version["id"]), wiki_page_title=release.wiki_title, due_date=release.date, description=self._version_description(release))
        updated_pages += 1

    refreshed = IndexSync(self.client, self.project_id).refresh_all()
    target_word = "处" if detail_mode == "inline" else "页"
    message = f"迁移完成：创建版本 {created_versions} 个，上传项目文件 {uploaded_files} 个，更新 Release Wiki {updated_pages} {target_word}，重建索引 {refreshed} 个 Release。"
    self._log(message)
    return {
        "ok": True,
        "preview": preview,
        "created_versions": created_versions,
        "uploaded_files": uploaded_files,
        "updated_release_pages": updated_pages,
        "refreshed_release_count": refreshed,
        "release_detail_mode": detail_mode,
        "release_detail_mode_label": _detail_mode_label(detail_mode),
        "message": message,
    }


def _detail_mode_label(mode: str) -> str:
    return "内联模式" if mode == "inline" else "一版本一页"


def _save_legacy_config(migrator: LegacyChangelogMigrator, categories: List[Dict[str, str]], *, single_list: bool, detail_mode: str) -> None:
    lines = [
        "# Release Tool Config",
        "",
        "本页面由旧 Changelog 迁移工具生成，用于配置当前项目的 Release Wiki 管理结构。",
        "",
        CONFIG_BEGIN,
        "```yaml",
        "mode: single_list" if single_list else "mode: multi_list",
        "main_page: Release_Notes",
        f"release_detail_mode: {detail_mode}",
    ]
    if detail_mode == "page":
        if single_list:
            lines.append(f"release_page_prefix: Release_{categories[0]['key']}_FW_")
        else:
            lines.append("release_page_prefix: Release_{category}_FW_")
    if not single_list:
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
    migrator.client.put_wiki_page(migrator.project_id, CONFIG_PAGE_TITLE, "\n".join(lines), "legacy changelog migration config")


def _create_legacy_structure(migrator: LegacyChangelogMigrator, categories: List[Dict[str, str]], *, single_list: bool, detail_mode: str) -> None:
    if single_list:
        migrator.client.put_wiki_page(migrator.project_id, "Release_Notes", migrator._single_list_placeholder(categories[0]["title"]), "legacy changelog migration structure")
        return

    main_lines = [
        "# Release Notes",
        "",
        f"固件 bin 存放在 [项目文件](/projects/{migrator.project_id}/files)，Wiki 记录版本变更和索引。",
        "",
        "## Product Lines",
        "",
    ]
    for category in categories:
        main_lines.append(f"- [[Release_Notes_{category['key']}|{category['title']}]]")
    migrator.client.put_wiki_page(migrator.project_id, "Release_Notes", "\n".join(main_lines).rstrip() + "\n", "legacy changelog migration structure")

    for category in categories:
        key = category["key"]
        title = category["title"]
        if detail_mode == "inline":
            migrator.client.put_wiki_page(
                migrator.project_id,
                f"Release_Notes_{key}",
                f"# {title}\n\n[[Release_Notes|返回 Release Notes]]\n\n## 版本列表\n\n",
                "legacy changelog migration structure",
                parent_title="Release_Notes",
            )
        else:
            migrator.client.put_wiki_page(
                migrator.project_id,
                f"Release_Notes_{key}",
                f"# {title}\n\n[[Release_Notes|返回 Release Notes]]\n\n## Version List\n\n{{{{include(Release_Notes_{key}_List)}}}}\n",
                "legacy changelog migration structure",
                parent_title="Release_Notes",
            )
            migrator.client.put_wiki_page(
                migrator.project_id,
                f"Release_Notes_{key}_List",
                f"# {title} 版本列表\n\n",
                "legacy changelog migration structure",
                parent_title=f"Release_Notes_{key}",
            )


def _legacy_inline_container(release, *, single_list: bool) -> str:
    return "Release_Notes" if single_list else f"Release_Notes_{release.model}"
