"""Redmine REST API 客户端。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import requests


class RedmineError(Exception):
    pass


VERSION_DESCRIPTION_LIMIT = 255


def _limit_version_description(value: str) -> str:
    text = (value or "").strip()
    if len(text) <= VERSION_DESCRIPTION_LIMIT:
        return text
    return text[: VERSION_DESCRIPTION_LIMIT - 3].rstrip() + "..."


class RedmineClient:
    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        *,
        api_key: str = "",
        auth_mode: str = "password",
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_mode = auth_mode
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json; charset=utf-8"})

        api_key = (api_key or "").strip()
        if auth_mode == "api_key" or api_key:
            if not api_key:
                raise RedmineError("请填写 Redmine API Key")
            self.session.headers.update({"X-Redmine-API-Key": api_key})
        else:
            self.session.auth = (username, password)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = self.session.request(method, self._url(path), timeout=60, **kwargs)
        except requests.RequestException as exc:
            raise RedmineError(f"Redmine {method} {path} 请求失败：{exc}") from exc

        if resp.status_code == 401:
            raise RedmineError("登录失败：用户名密码或 API Key 错误，或无 API 访问权限")
        if resp.status_code == 403:
            raise RedmineError(f"权限不足：{path}")
        if resp.status_code == 404:
            raise RedmineError(f"资源不存在：{path}")
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise RedmineError(f"Redmine {method} {path} 返回 HTTP {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            detail = resp.text[:500]
            raise RedmineError(f"Redmine {method} {path} 返回了无法解析的 JSON: {detail}") from exc

    def test_login(self) -> dict[str, Any]:
        return self._request("GET", "/my/account.json")

    def list_projects(self, *, membership: bool = False) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        membership_param = "&membership=true" if membership else ""
        while True:
            data = self._request("GET", f"/projects.json?limit={limit}&offset={offset}{membership_param}")
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

    def get_wiki_page(self, project_id: str, title: str, *, include_attachments: bool = False) -> dict[str, Any] | None:
        suffix = "?include=attachments" if include_attachments else ""
        try:
            data = self._request(
                "GET",
                f"/projects/{quote(project_id)}/wiki/{quote(title, safe='')}.json{suffix}",
            )
            return data.get("wiki_page")
        except RedmineError as exc:
            if "404" in str(exc) or "资源不存在" in str(exc):
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
                "description": _limit_version_description(description),
            }
        }
        data = self._request("POST", f"/projects/{quote(project_id)}/versions.json", json=payload)
        return data["version"]

    def update_version(self, version_id: int, **fields: Any) -> None:
        if "description" in fields:
            fields["description"] = _limit_version_description(str(fields.get("description") or ""))
        self._request("PUT", f"/versions/{version_id}.json", json={"version": fields})

    def upload_file(self, filename: str, content: bytes) -> str:
        upload_url = f"{self.base_url}/uploads.json?filename={quote(filename)}"
        try:
            resp = self.session.post(
                upload_url,
                data=content,
                headers={"Content-Type": "application/octet-stream"},
                timeout=120,
            )
        except requests.RequestException as exc:
            raise RedmineError(f"上传失败 {filename}: {exc}") from exc
        if resp.status_code >= 400:
            raise RedmineError(f"上传失败 {filename}: HTTP {resp.status_code} {resp.text[:200]}")
        try:
            data = resp.json()
            token = data["upload"]["token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RedmineError(f"上传失败 {filename}: Redmine 返回内容无法解析") from exc
        return token

    def download_content_url(self, content_url: str) -> bytes:
        url = content_url
        if content_url.startswith("/"):
            url = f"{self.base_url}{content_url}"
        try:
            resp = self.session.get(url, timeout=120)
        except requests.RequestException as exc:
            raise RedmineError(f"下载附件失败: {exc}") from exc
        if resp.status_code >= 400:
            raise RedmineError(f"下载附件失败: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.content

    def list_project_files(self, project_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/projects/{quote(project_id)}/files.json")
        return data.get("files", []) if isinstance(data, dict) else []

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
        return data.get("file", {}) if isinstance(data, dict) else {}


RELEASE_PAGE_RE = re.compile(r"^Release_[A-Za-z0-9_+-]+(?:_NP500)?_FW_", re.I)
