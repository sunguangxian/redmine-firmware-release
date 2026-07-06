"""发布流程编排。"""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import quote, urlparse

from .attachment_policy import sha256_hex, validate_attachment_batch
from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError
from .release_lock import PublishLockTimeout, acquire_publish_lock
from .release_page import (
    ReleaseForm,
    build_inline_release_block,
    build_release_markdown,
    delete_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    merge_release_files,
    parse_inline_ref,
    parse_release_files,
    parse_release_page,
    replace_inline_release_block,
)
from .release_structure_guard import ensure_release_structure_ready

_SHA_RE = re.compile(r"SHA256:\s*([0-9a-fA-F]{64})")
StageProgress = Callable[[str, str], None]


class ReleasePublisher:
    def __init__(self, client: RedmineClient):
        self.client = client

    def publish(
        self,
        form: ReleaseForm,
        logs: list[str] | None = None,
        progress: StageProgress | None = None,
        plan: dict[str, Any] | None = None,
    ) -> str:
        self._log(logs, f"开始处理版本：{form.version_name}")
        if form.files:
            self._progress(progress, "file", "running")
            try:
                self._preflight_release(form, logs)
            except Exception:
                self._progress(progress, "file", "failed")
                raise
        else:
            self._preflight_release(form, logs)
            self._progress(progress, "file", "skipped")
        if form.wiki_title and not form.files and form.replace_attachments:
            form.replace_attachments = False
            self._log(logs, "编辑版本未选择新附件，自动保留已有附件列表")
        lock_key = f"{form.project_id}:{form.version_name}".lower()
        self._log(logs, "发布控制：申请跨进程发布锁，避免多用户并发覆盖")
        try:
            with acquire_publish_lock(lock_key):
                self._log(logs, "发布控制：发布锁获取成功")
                return self._publish_locked(form, logs, progress, plan)
        except PublishLockTimeout as exc:
            self._log(logs, f"发布控制：发布锁获取失败：{exc}")
            raise RedmineError(str(exc)) from exc

    def _publish_locked(
        self,
        form: ReleaseForm,
        logs: list[str] | None = None,
        progress: StageProgress | None = None,
        plan: dict[str, Any] | None = None,
    ) -> str:
        try:
            self._progress(progress, "release", "running")
            self._log(logs, "检查项目 Wiki 发布结构")
            index_sync, profile = ensure_release_structure_ready(self.client, form.project_id, logs)
            if self._is_inline_profile(profile):
                return self._publish_locked_inline(form, index_sync, profile, logs, progress, plan)
            self._log(logs, f"项目发布结构：{profile.mode}")
            self._validate_category(form, index_sync, profile, logs)
            if plan and plan.get("mode") == "page":
                planned_title = str(plan.get("target_page") or "").strip()
                if planned_title:
                    form.wiki_title = planned_title
                    self._log(logs, f"使用发布计划目标页面：{planned_title}")
            else:
                generated_title = self._configured_release_title(form, index_sync, profile)
                if generated_title and not form.wiki_title:
                    form.wiki_title = generated_title
                    self._log(logs, f"按项目配置生成 Release 页面：{generated_title}")
            version_name = self._configured_version_name(form, index_sync, profile)
            version = self._get_or_create_version(form, logs, version_name=version_name)
            self._progress(progress, "release", "success")
        except Exception:
            self._progress(progress, "release", "failed")
            raise

        title = form.page_title
        try:
            self._progress(progress, "wiki", "running")
            existing = self.client.get_wiki_page(form.project_id, title)
            existing_text = (existing or {}).get("text", "")
            self._log(logs, f"Wiki 页面：{'编辑已有页面' if existing else '创建新页面'} {title}")
            old_files = list(plan.get("old_files") or []) if plan and plan.get("mode") == "page" else (parse_release_files(existing_text) if existing_text else [])
        except Exception:
            self._progress(progress, "wiki", "failed")
            raise

        try:
            if form.files:
                self._progress(progress, "file", "running")
            else:
                self._progress(progress, "file", "skipped")
            self._log(
                logs,
                f"附件策略：{plan.get('attachment_plan') if plan and plan.get('mode') == 'page' else ('替换旧附件列表' if form.replace_attachments else '保留旧附件并追加')}；"
                f"已有 {len(old_files)} 个，本次选择 {len(form.files)} 个",
            )
            new_files = self._upload_files(form, version["id"], logs)
            linked_files = merge_release_files(
                old_files,
                new_files,
                replace=form.replace_attachments,
            )
            self._log(logs, f"附件列表合并完成：最终 {len(linked_files)} 个")
            if form.files:
                self._progress(progress, "file", "success")
        except Exception:
            self._progress(progress, "file", "failed")
            raise

        try:
            self._progress(progress, "wiki", "running")
            self._assert_wiki_unchanged(form.project_id, title, existing_text, logs)
            markdown = build_release_markdown(form, version["id"], linked_files, main_page=profile.main_page)
            comment = "release tool update" if existing else "release tool create"
            self.client.put_wiki_page(form.project_id, title, markdown, comment)
            self._log(logs, "Wiki 页面写入完成")
            self._progress(progress, "wiki", "success")
        except Exception:
            self._progress(progress, "wiki", "failed")
            raise

        try:
            self._progress(progress, "release", "running")
            self.client.update_version(
                version["id"],
                wiki_page_title=title,
                due_date=form.release_date,
                description=self._version_description(form),
            )
            self._log(logs, "Redmine 版本信息更新完成")
            self._progress(progress, "release", "success")
        except Exception:
            self._progress(progress, "release", "failed")
            raise

        try:
            self._progress(progress, "index", "running")
            index_sync.sync_after_publish(title, markdown)
            self._log(logs, "版本索引同步完成")
            self._progress(progress, "index", "success")
        except Exception:
            self._progress(progress, "index", "failed")
            raise
        return title

    def _publish_locked_inline(
        self,
        form: ReleaseForm,
        index_sync,
        profile,
        logs: list[str] | None = None,
        progress: StageProgress | None = None,
        plan: dict[str, Any] | None = None,
    ) -> str:
        try:
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
        if plan and plan.get("mode") == "inline":
            container_page = str(plan.get("container_page") or "").strip()
            new_block_id = str(plan.get("block_id") or "").strip()
            old_block_id = str(plan.get("old_block_id") or old_block_id).strip()
            is_edit = bool(plan.get("is_edit"))
            form.wiki_title = None
        else:
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
            new_block_id = ""

        try:
            self._progress(progress, "wiki", "running")
            page = self.client.get_wiki_page(form.project_id, container_page)
            current_text = (page or {}).get("text", "")
            if plan and plan.get("mode") == "inline":
                old_files = list(plan.get("old_files") or [])
            else:
                old_block = extract_inline_release_block(current_text, old_block_id)
                old_display_version = self._inline_display_version(old_block_id, old_block)
                new_block_id = self._next_block_id(old_block_id, old_display_version, form.version_name, is_edit)
                old_files = parse_release_files(old_block) if old_block else []
            if is_edit and old_block_id != new_block_id:
                self._log(logs, f"内联编辑目标块：{old_block_id} -> {new_block_id}")
            elif is_edit and old_block_id != form.version_name.strip():
                self._log(logs, f"内联编辑保留唯一块标识：{old_block_id}，显示版本：{form.version_name.strip()}")
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
            self._assert_wiki_unchanged(form.project_id, container_page, current_text, logs)
            base_text = current_text
            if old_block_id and old_block_id != new_block_id:
                base_text = delete_inline_release_block(base_text, old_block_id)
                self._log(logs, f"已删除旧内联版本块：{old_block_id}")
            block = build_inline_release_block(
                form,
                int(version["id"]),
                linked_files,
                block_id=new_block_id,
                container_page=container_page,
            )
            new_text = replace_inline_release_block(base_text, new_block_id, block)
            parent_title = self._inline_parent_title(profile, container_page)
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

    def _is_inline_profile(self, profile) -> bool:
        return getattr(profile, "release_detail_mode", "inline") == "inline"

    def _inline_display_version(self, block_id: str, block: str) -> str:
        if not block:
            return ""
        try:
            parsed = parse_release_page(inline_ref("_", block_id), block)
            return str(parsed.get("version_name") or "").strip()
        except Exception:
            return ""

    def _next_block_id(self, old_block_id: str, old_display_version: str, new_display_version: str, is_edit: bool) -> str:
        new_display_version = (new_display_version or "").strip()
        if not is_edit:
            return new_display_version
        old_block_id = (old_block_id or "").strip()
        old_display_version = (old_display_version or "").strip()
        if old_block_id and old_display_version and old_block_id != old_display_version:
            return old_block_id
        return new_display_version

    def _inline_parent_title(self, profile, container_page: str) -> str | None:
        if profile.mode != "multi_list":
            return None
        for category in profile.categories:
            if category.list_page == container_page:
                return category.hub if category.list_page != category.hub else profile.main_page
        return None

    def _assert_wiki_unchanged(self, project_id: str, title: str, expected_text: str, logs: list[str] | None = None) -> None:
        latest = self.client.get_wiki_page(project_id, title)
        latest_text = (latest or {}).get("text", "")
        if (expected_text or "") != latest_text:
            self._log(logs, f"Wiki 冲突检测失败：{title}")
            raise RedmineError(f"Wiki 页面已被其他用户修改：{title}。请刷新后重新发布，避免覆盖他人改动。")
        self._log(logs, f"Wiki 冲突检测通过：{title}")

    def _preflight_release(self, form: ReleaseForm, logs: list[str] | None = None) -> None:
        if not form.files:
            self._log(logs, "发布预检查：未选择新附件，跳过附件内容校验")
            return
        self._log(logs, "发布预检查：校验附件大小并生成 SHA256")
        validate_attachment_batch(form.files)
        files: list[tuple[str, str, bytes]] = []
        for filename, description, content in form.files:
            digest = sha256_hex(content)
            desc = (description or "").strip()
            sha_desc = f"SHA256: {digest}"
            files.append((filename, f"{desc}; {sha_desc}" if desc else sha_desc, content))
        form.files = files
        self._log(logs, "发布预检查完成：附件校验通过，已生成 SHA256")

    def _validate_category(self, form: ReleaseForm, index_sync, profile, logs: list[str] | None = None) -> None:
        if profile.mode != "multi_list":
            self._log(logs, "项目不是 multi_list，版本分类允许为空")
            return

        if not form.product_line.strip():
            self._log(logs, "multi_list 分类校验失败：版本分类为空")
            raise RedmineError("当前项目配置为 multi_list，发布或编辑版本时必须填写版本分类。")

        category = index_sync._categorize(
            form.page_title,
            f"**Product Line:** {form.product_line}",
            ver=form.version_name,
            commit=form.commit,
            categories=profile.categories,
        )
        if category:
            self._log(logs, f"multi_list 分类校验通过：{form.product_line}")
            return

        category_names = "、".join(category.title or category.key for category in profile.categories)
        self._log(logs, f"multi_list 分类校验失败：{form.product_line} 不在配置中")
        raise RedmineError(
            f"版本分类“{form.product_line}”未匹配当前项目 Release_Tool_Config 中的分类：{category_names}"
        )

    def _configured_release_title(self, form: ReleaseForm, index_sync, profile) -> str:
        prefix = (getattr(profile, "release_page_prefix", "") or "").strip()
        if not prefix:
            return ""
        category = ""
        if profile.mode == "multi_list":
            category = index_sync._categorize(
                form.page_title,
                f"**Product Line:** {form.product_line}",
                ver=form.version_name,
                commit=form.commit,
                categories=profile.categories,
            )
        category = category or form.product_line or form.proj_tag
        prefix = (
            prefix.replace("{category}", category)
            .replace("{model}", category)
            .replace("{project}", form.proj_tag)
        )
        return f"{prefix}{form.wiki_suffix}"

    def _configured_version_name(self, form: ReleaseForm, index_sync, profile) -> str:
        return form.version_name.strip()

    def list_releases(self, project_id: str) -> list[dict]:
        sync = IndexSync(self.client, project_id)
        try:
            profile = sync.discover_profile()
        except RedmineError:
            profile = None
        if profile and self._is_inline_profile(profile):
            rows = []
            category_titles = {category.key: category.title for category in getattr(profile, "categories", [])}
            for item in sync._build_items(profile):
                rows.append(
                    {
                        "title": item["page"],
                        "display_title": f"{item.get('container_page') or item['page']} / {item['ver']}",
                        "container_page": item.get("container_page", ""),
                        "block_id": item.get("block_id", ""),
                        "version": item["ver"],
                        "date": item["date"],
                        "product_line": category_titles.get(item.get("cat", ""), "") or item.get("product_line", ""),
                        "summary": item.get("summary", ""),
                    }
                )
            rows.sort(key=lambda x: x["date"], reverse=True)
            return rows
        pages = self.client.get_wiki_index(project_id)
        releases = []
        category_titles = {category.key: category.title for category in getattr(profile, "categories", [])} if profile else {}
        for item in pages:
            title = item["title"]
            if not title.startswith("Release_") or "_FW_" not in title:
                continue
            page = self.client.get_wiki_page(project_id, title)
            if not page:
                continue
            text = page.get("text", "")
            parsed = parse_release_page(title, text)
            category = sync._categorize(
                title,
                text,
                parsed.get("version_name", ""),
                parsed.get("commit", ""),
                getattr(profile, "categories", []) if profile else [],
            )
            releases.append(
                {
                    "title": title,
                    "display_title": title,
                    "container_page": "",
                    "block_id": "",
                    "version": parsed["version_name"],
                    "date": parsed["release_date"],
                    "product_line": category_titles.get(category, parsed["product_line"]),
                    "summary": (parsed["changelog"].splitlines() or [""])[0],
                }
            )
        releases.sort(key=lambda x: x["date"], reverse=True)
        return releases

    def _get_or_create_version(self, form: ReleaseForm, logs: list[str] | None = None, version_name: str | None = None) -> dict:
        name = (version_name or form.version_name).strip()
        for version in self.client.list_versions(form.project_id):
            if version.get("name", "").strip() == name:
                self._log(logs, f"复用已有 Redmine 版本：{name}")
                return version

        version = self.client.create_version(
            form.project_id,
            name,
            form.release_date,
            self._version_description(form),
        )
        self._log(logs, f"创建 Redmine 版本完成：{name}")
        return version

    def _version_description(self, form: ReleaseForm) -> str:
        lines = [
            f"commit: {form.commit}",
            f"固件文件: /projects/{form.project_id}/files",
            "",
        ]
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(form.changelog_items, 1))
        return "\n".join(lines).strip()

    def _upload_files(self, form: ReleaseForm, version_id: int, logs: list[str] | None = None) -> list[dict]:
        linked: list[dict] = []
        existing_by_name = self._project_files_by_name(form.project_id, version_id)
        if not form.files:
            self._log(logs, "本次未选择新附件，跳过附件上传")
        for filename, description, content in form.files:
            if not content:
                self._log(logs, f"跳过空附件：{filename}")
                continue
            existing = existing_by_name.get(filename)
            if existing:
                self._ensure_same_existing_file(existing, filename, description, content, logs)
                self._log(logs, f"附件已存在且 SHA256 一致，复用项目文件：{filename}")
                linked.append(
                    {
                        "filename": filename,
                        "description": existing.get("description") or description,
                        "url": self._project_file_url(existing, filename),
                    }
                )
                continue

            token = self.client.upload_file(filename, content)
            file_obj = self.client.create_project_file(
                form.project_id, version_id, filename, token
            )
            if not self._project_file_url(file_obj, filename):
                file_obj = self._project_files_by_name(form.project_id, version_id).get(filename, {})
            url = self._project_file_url(file_obj, filename)
            linked.append({"filename": filename, "description": description, "url": url})
            self._log(logs, f"附件上传完成：{filename}")
        return linked

    def _ensure_same_existing_file(
        self,
        existing: dict,
        filename: str,
        description: str,
        content: bytes,
        logs: list[str] | None = None,
    ) -> None:
        new_sha = self._sha_from_description(description) or sha256_hex(content)
        old_sha = self._sha_from_description(existing.get("description") or "")
        if not old_sha:
            content_url = existing.get("content_url") or self._project_file_url(existing, filename)
            if not content_url:
                raise RedmineError(f"项目文件已存在但无法确认内容：{filename}。请改名后重新上传。")
            self._log(logs, f"同名附件缺少 SHA256 说明，下载旧文件校验：{filename}")
            old_sha = sha256_hex(self.client.download_content_url(content_url))
        if old_sha.lower() != new_sha.lower():
            raise RedmineError(
                f"同名附件内容不一致：{filename}。"
                "为避免复用旧文件导致版本异常，请修改文件名或先处理 Redmine 项目文件中的同名文件。"
            )

    def _sha_from_description(self, description: str) -> str:
        match = _SHA_RE.search(description or "")
        return match.group(1).lower() if match else ""

    def _project_files_by_name(self, project_id: str, version_id: int) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for item in self.client.list_project_files(project_id):
            filename = item.get("filename")
            if not filename or (item.get("version") or {}).get("id") != version_id:
                continue
            result.setdefault(filename, item)
        return result

    def _project_file_url(self, file_obj: dict, filename: str) -> str | None:
        url = file_obj.get("content_url", "")
        if url and url.startswith("http"):
            return urlparse(url).path
        if url:
            return url
        if file_obj.get("id"):
            return f"/attachments/download/{file_obj['id']}/{quote(filename)}"
        return None

    def _log(self, logs: list[str] | None, message: str) -> None:
        if logs is not None:
            logs.append(message)

    def _progress(self, progress: StageProgress | None, stage: str, status: str) -> None:
        if progress is not None:
            progress(stage, status)
