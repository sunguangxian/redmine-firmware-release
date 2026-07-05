"""发布流程编排。"""

from __future__ import annotations

import threading
from collections import defaultdict
from urllib.parse import quote, urlparse

from .attachment_policy import sha256_hex, validate_attachment_batch
from .index_sync import IndexSync
from .redmine_api import RedmineClient, RedmineError
from .release_page import (
    ReleaseForm,
    build_release_markdown,
    merge_release_files,
    parse_release_files,
    parse_release_page,
)

_RELEASE_LOCKS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


class ReleasePublisher:
    def __init__(self, client: RedmineClient):
        self.client = client

    def publish(self, form: ReleaseForm, logs: list[str] | None = None) -> str:
        self._log(logs, f"开始处理版本：{form.version_name}")
        self._preflight_release(form, logs)
        lock_key = f"{form.project_id}:{form.version_name}".lower()
        self._log(logs, "发布控制：同一项目同一版本串行执行，避免并发覆盖")
        with _RELEASE_LOCKS[lock_key]:
            return self._publish_locked(form, logs)

    def _publish_locked(self, form: ReleaseForm, logs: list[str] | None = None) -> str:
        index_sync = IndexSync(self.client, form.project_id)
        self._log(logs, "读取项目 Release_Tool_Config 配置")
        profile = index_sync.discover_profile()
        self._log(logs, f"项目发布结构：{profile.mode}")
        self._validate_category(form, index_sync, profile, logs)
        generated_title = self._configured_release_title(form, index_sync, profile)
        if generated_title and not form.wiki_title:
            form.wiki_title = generated_title
            self._log(logs, f"按项目配置生成 Release 页面：{generated_title}")
        version_name = self._configured_version_name(form, index_sync, profile)

        version = self._get_or_create_version(form, logs, version_name=version_name)
        title = form.page_title
        existing = self.client.get_wiki_page(form.project_id, title)
        existing_text = (existing or {}).get("text", "")
        self._log(logs, f"Wiki 页面：{'编辑已有页面' if existing else '创建新页面'} {title}")

        old_files = parse_release_files(existing_text) if existing_text else []
        self._log(
            logs,
            f"附件策略：{'替换旧附件列表' if form.replace_attachments else '保留旧附件并追加'}；"
            f"已有 {len(old_files)} 个，本次选择 {len(form.files)} 个",
        )
        new_files = self._upload_files(form, version["id"], logs)
        linked_files = merge_release_files(
            old_files,
            new_files,
            replace=form.replace_attachments,
        )
        self._log(logs, f"附件列表合并完成：最终 {len(linked_files)} 个")

        markdown = build_release_markdown(form, version["id"], linked_files)

        comment = "release tool update" if existing else "release tool create"
        self.client.put_wiki_page(form.project_id, title, markdown, comment)
        self._log(logs, "Wiki 页面写入完成")

        self.client.update_version(
            version["id"],
            wiki_page_title=title,
            due_date=form.release_date,
            description=self._version_description(form),
        )
        self._log(logs, "Redmine 版本信息更新完成")

        index_sync.sync_after_publish(title, markdown)
        self._log(logs, "版本索引同步完成")
        return title

    def _preflight_release(self, form: ReleaseForm, logs: list[str] | None = None) -> None:
        self._log(logs, "发布预检查：校验附件类型、大小和 SHA256")
        validate_attachment_batch(form.files)
        files: list[tuple[str, str, bytes]] = []
        for filename, description, content in form.files:
            digest = sha256_hex(content)
            desc = (description or "").strip()
            sha_desc = f"SHA256: {digest}"
            files.append((filename, f"{desc}; {sha_desc}" if desc else sha_desc, content))
        form.files = files
        self._log(logs, "发布预检查完成：附件校验通过，已生成 SHA256")

    def _validate_category(self, form: ReleaseForm, index_sync: IndexSync, profile, logs: list[str] | None = None) -> None:
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

    def _configured_release_title(self, form: ReleaseForm, index_sync: IndexSync, profile) -> str:
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

    def _configured_version_name(self, form: ReleaseForm, index_sync: IndexSync, profile) -> str:
        return form.version_name.strip()

    def list_releases(self, project_id: str) -> list[dict]:
        pages = self.client.get_wiki_index(project_id)
        releases = []
        for item in pages:
            title = item["title"]
            if not title.startswith("Release_") or "_FW_" not in title:
                continue
            page = self.client.get_wiki_page(project_id, title)
            if not page:
                continue
            parsed = parse_release_page(title, page.get("text", ""))
            releases.append(
                {
                    "title": title,
                    "version": parsed["version_name"],
                    "date": parsed["release_date"],
                    "product_line": parsed["product_line"],
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
                self._log(logs, f"附件已存在，复用项目文件：{filename}")
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
