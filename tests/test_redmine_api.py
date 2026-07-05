import unittest
from unittest.mock import patch

import requests

from release_tool.redmine_api import RedmineClient, RedmineError


class FakeRedmineClient(RedmineClient):
    def __init__(self):
        self.paths = []

    def _request(self, method, path, **kwargs):
        self.paths.append(path)
        if "offset=0" in path:
            return {
                "files": [{"id": 1, "filename": "a.bin"}],
                "total_count": 2,
            }
        if "offset=100" in path:
            return {
                "files": [{"id": 2, "filename": "b.bin"}],
                "total_count": 2,
            }
        return {"files": [], "total_count": 2}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", content=b"x", headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses=None):
        self.headers = {}
        self.auth = None
        self.responses = list(responses or [])
        self.calls = []
        self.post_calls = []
        self.get_calls = []
        self.post_response = FakeResponse(json_data={"upload": {"token": "token-1"}})
        self.get_response = FakeResponse(content=b"payload")

    def request(self, method, url, timeout, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, data, headers, timeout):
        self.post_calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return self.post_response

    def get(self, url, timeout):
        self.get_calls.append({"url": url, "timeout": timeout})
        return self.get_response


class RedmineApiTest(unittest.TestCase):
    def _client(self, session):
        client = RedmineClient("http://redmine.local", "user", "pass")
        client.session = session
        return client

    def test_list_project_files_reads_all_pages(self):
        client = FakeRedmineClient()
        files = client.list_project_files("dp580")
        self.assertEqual([item["filename"] for item in files], ["a.bin", "b.bin"])
        self.assertEqual(len(client.paths), 2)
        self.assertIn("limit=100&offset=0", client.paths[0])
        self.assertIn("limit=100&offset=100", client.paths[1])

    def test_request_retries_transient_get_failure(self):
        session = FakeSession([requests.ConnectionError("reset"), FakeResponse(status_code=200, json_data={"ok": True})])
        client = self._client(session)

        with patch("release_tool.redmine_api.time.sleep"):
            self.assertEqual(client._request("GET", "/projects.json"), {"ok": True})
        self.assertEqual(len(session.calls), 2)

    def test_request_retries_429_and_respects_retry_after(self):
        session = FakeSession(
            [
                FakeResponse(status_code=429, text="busy", headers={"Retry-After": "0.5"}),
                FakeResponse(status_code=200, json_data={"ok": True}),
            ]
        )
        client = self._client(session)

        with patch.dict(
            "os.environ",
            {"RELEASE_TOOL_REDMINE_RETRIES": "1", "RELEASE_TOOL_REDMINE_TIMEOUT": "7"},
            clear=False,
        ), patch("release_tool.redmine_api.time.sleep") as sleep:
            data = client._request("GET", "/projects.json")

        self.assertEqual(data, {"ok": True})
        self.assertEqual([call["timeout"] for call in session.calls], [7, 7])
        sleep.assert_called_once_with(0.5)

    def test_request_does_not_retry_project_file_creation(self):
        session = FakeSession([requests.ConnectionError("reset")])
        client = self._client(session)

        with self.assertRaises(RedmineError):
            client._request("POST", "/projects/dp5x/files.json", json={})
        self.assertEqual(len(session.calls), 1)

    def test_files_post_status_is_not_retried(self):
        session = FakeSession([FakeResponse(status_code=503, text="unavailable")])
        client = self._client(session)

        with patch.dict("os.environ", {"RELEASE_TOOL_REDMINE_RETRIES": "3"}, clear=False):
            with self.assertRaisesRegex(RedmineError, "HTTP 503"):
                client._request("POST", "/projects/demo/files.json", json={})

        self.assertEqual(len(session.calls), 1)

    def test_request_wraps_request_exception(self):
        session = FakeSession([requests.Timeout("timeout")])
        client = self._client(session)

        with patch.dict("os.environ", {"RELEASE_TOOL_REDMINE_RETRIES": "0"}, clear=False):
            with self.assertRaisesRegex(RedmineError, "请求失败"):
                client._request("GET", "/projects.json")

    def test_upload_and_download_use_configured_file_timeout(self):
        session = FakeSession()
        client = self._client(session)

        with patch.dict("os.environ", {"RELEASE_TOOL_REDMINE_FILE_TIMEOUT": "9"}, clear=False):
            token = client.upload_file("fw.bin", b"123")
            content = client.download_content_url("/attachments/download/1/fw.bin")

        self.assertEqual(token, "token-1")
        self.assertEqual(content, b"payload")
        self.assertEqual(session.post_calls[0]["timeout"], 9)
        self.assertEqual(session.get_calls[0]["timeout"], 9)


if __name__ == "__main__":
    unittest.main()
