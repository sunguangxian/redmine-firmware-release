"""发布流程编排。"""

from __future__ import annotations

from urllib.parse import quote, urlparse

from .index_sync import IndexSync
from .redmine_api import RedmineClient
from .release_page import (
    ReleaseForm,
    build_release_markdown,
    merge_release_files,
    parse_release_files,
    parse_release_page,
)


class ReleasePublisher:
    def __init__(self, client: RedmineClient):
        self.client = client

    def publish(self, form: ReleaseForm) -> str:
        # 发布前先确认项目已经配置 Release_Tool_Config。
        # 没有配置页时直接抛错，避免创建版本/上传附件后才发现无法同步索引。
        index_sync = IndexSync(self.client, form.project_id)
        index_sync.discover_profile()

        version = self._get_or_create_version(form)
        title = form.page_title
        existing = self.client.get_wiki_page(form.project_id, title)
        existing_text = (existing or {}).get("text", "")

        old_files = parse_release_files(existing_text) if existing_text else []
        new_files = self._upload_files(form, version["id"])
        linked_files = merge_release_files(
            old_files,
            new_files,
            replace=form.replace_attachments,
        )

        markdown = build_release_markdown(form, version["id"], linked_files)

        comment = "release tool update" if existing else "release tool create"
        self.client.put_wiki_page(form.project_id, title, markdown, comment)

        self.client.update_version(
            version["id"],
            wiki_page_title=title,
            due_date=form.release_date,
            description=self._version_description(form),
        )

        index_sync.sync_after_publish(title, markdown)
        return title

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

    def _get_or_create_version(self, form: ReleaseForm) -> dict:
        name = form.version_name.strip()
        for version in self.client.list_versions(form.project_id):
            if version.get("name", "").strip() == name:
                return version

        return self.client.create_version(
            form.project_id,
            name,
            form.release_date,
            self._version_description(form),
        )

    def _version_description(self, form: ReleaseForm) -> str:
        lines = [
            f"commit: {form.commit}",
            f"固件文件: /projects/{form.project_id}/files",
            "",
        ]
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(form.changelog_items, 1))
        return "\n".join(lines).strip()

    def _upload_files(self, form: ReleaseForm, version_id: int) -> list[dict]:
        linked: list[dict] = []
        existing_by_name = self._project_files_by_name(form.project_id, version_id)
        for filename, description, content in form.files:
            if not content:
                continue
            existing = existing_by_name.get(filename)
            if existing:
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
