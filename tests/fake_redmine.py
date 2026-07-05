from __future__ import annotations

from typing import Any


class FakeRedmineClient:
    base_url = "http://redmine.example"

    def __init__(self):
        self.pages: dict[str, dict[str, Any]] = {}
        self.versions: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.uploads: dict[str, bytes] = {}
        self.next_version_id = 1
        self.next_file_id = 1

    def seed_page(self, title: str, text: str, parent_title: str = "") -> None:
        self.pages[title] = {"title": title, "text": text, "parent": {"title": parent_title} if parent_title else {}}

    def seed_version(self, name: str, version_id: int | None = None) -> dict[str, Any]:
        item = {"id": version_id or self.next_version_id, "name": name}
        self.next_version_id = max(self.next_version_id, int(item["id"]) + 1)
        self.versions.append(item)
        return item

    def get_wiki_index(self, project_id: str) -> list[dict[str, Any]]:
        return [{"title": title} for title in sorted(self.pages)]

    def get_wiki_page(self, project_id: str, title: str, *, include_attachments: bool = False) -> dict[str, Any] | None:
        page = self.pages.get(title)
        return dict(page) if page else None

    def put_wiki_page(self, project_id: str, title: str, text: str, comment: str = "", parent_title: str | None = None) -> None:
        self.pages[title] = {
            "title": title,
            "text": text,
            "parent": {"title": parent_title} if parent_title else (self.pages.get(title, {}).get("parent") or {}),
        }

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.versions]

    def create_version(self, project_id: str, name: str, due_date: str, description: str) -> dict[str, Any]:
        item = {"id": self.next_version_id, "name": name, "due_date": due_date, "description": description}
        self.next_version_id += 1
        self.versions.append(item)
        return dict(item)

    def update_version(self, version_id: int, **fields: Any) -> None:
        for item in self.versions:
            if int(item["id"]) == int(version_id):
                item.update(fields)
                return

    def upload_file(self, filename: str, content: bytes) -> str:
        token = f"token-{len(self.uploads) + 1}"
        self.uploads[token] = content
        return token

    def create_project_file(self, project_id: str, version_id: int, filename: str, token: str) -> dict[str, Any]:
        item = {
            "id": self.next_file_id,
            "filename": filename,
            "description": "",
            "content_url": f"/attachments/download/{self.next_file_id}/{filename}",
            "version": {"id": version_id},
        }
        self.next_file_id += 1
        self.files.append(item)
        return dict(item)

    def list_project_files(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.files]
