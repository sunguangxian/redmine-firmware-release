"""Redmine REST API 客户端。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import requests


class RedmineError(Exception):
    pass


class RedmineClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Content-Type": "application/json; charset=utf-8"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self.session.request(method, self._url(path), timeout=60, **kwargs)
        if resp.status_code == 401:
            raise RedmineError("登录失败：用户名或密码错误，或无 API 访问权限")
        if resp.status_code == 403:
            raise RedmineError(f"权限不足：{path}")
        if resp.status_code == 404:
            raise RedmineError(f"资源不存在：{path}")
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise RedmineError(f"HTTP {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def test_login(self) -> dict[str, Any]:
        return self._request("GET", "/my/account.json")

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            data = self._request("GET", f"/projects.json?limit={limit}&offset={offset}")
            batch = data.get("projects", [])
            projects.extend(batch)
            total = data.get("total_count", len(projects))
            offset += limit
            if offset >= total:
                break
        return [p for p in projects if p.get("status") != 5]

    def get_wiki_index(self, project_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/projects/{quote(project_id)}/wiki/index.json")
        return data.get("wiki_pages", [])

    def get_wiki_page(self, project_id: str, title: str) -> dict[str, Any] | None:
        try:
            data = self._request(
                "GET",
                f"/projects/{quote(project_id)}/wiki/{quote(title, safe='')}.json",
            )
            return data.get("wiki_page")
        except RedmineError as exc:
            if "404" in str(exc):
                return None
            raise

    def put_wiki_page(
        self,
        project_id: str,
        title: str,
        text: str,
        comment: str = "",
        parent_title: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"wiki_page": {"text": text, "comments": comment}}
        if parent_title:
            payload["wiki_page"]["parent_title"] = parent_title
        self._request(
            "PUT",
            f"/projects/{quote(project_id)}/wiki/{quote(title, safe='')}.json",
            json=payload,
        )

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        versions: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            data = self._request(
                "GET",
                f"/projects/{quote(project_id)}/versions.json?limit={limit}&offset={offset}",
            )
            batch = data.get("versions", [])
            versions.extend(batch)
            total = data.get("total_count", len(versions))
            offset += limit
            if offset >= total:
                break
        return versions

    def create_version(
        self,
        project_id: str,
        name: str,
        due_date: str,
        description: str,
    ) -> dict[str, Any]:
        payload = {
            "version": {
                "name": name,
                "status": "open",
                "due_date": due_date,
                "description": description,
            }
        }
        data = self._request("POST", f"/projects/{quote(project_id)}/versions.json", json=payload)
        return data["version"]

    def update_version(self, version_id: int, **fields: Any) -> None:
        self._request("PUT", f"/versions/{version_id}.json", json={"version": fields})

    def upload_file(self, filename: str, content: bytes) -> str:
        upload_url = f"{self.base_url}/uploads.json?filename={quote(filename)}"
        resp = self.session.post(
            upload_url,
            data=content,
            headers={"Content-Type": "application/octet-stream"},
            timeout=120,
        )
        if resp.status_code >= 400:
            raise RedmineError(f"上传失败 {filename}: HTTP {resp.status_code} {resp.text[:200]}")
        token = resp.json()["upload"]["token"]
        return token

    def create_project_file(
        self,
        project_id: str,
        version_id: int,
        filename: str,
        token: str,
    ) -> dict[str, Any]:
        payload = {
            "file": {
                "token": token,
                "filename": filename,
                "content_type": "application/octet-stream",
                "version_id": version_id,
            }
        }
        data = self._request("POST", f"/projects/{quote(project_id)}/files.json", json=payload)
        return data.get("file", {})


RELEASE_PAGE_RE = re.compile(r"^Release_[A-Za-z0-9]+(?:_NP500)?_FW_", re.I)
