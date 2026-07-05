import unittest
from unittest.mock import patch

import requests

from release_tool.redmine_api import RedmineClient


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


class RedmineApiTest(unittest.TestCase):
    def test_list_project_files_reads_all_pages(self):
        client = FakeRedmineClient()
        files = client.list_project_files("dp580")
        self.assertEqual([item["filename"] for item in files], ["a.bin", "b.bin"])
        self.assertEqual(len(client.paths), 2)
        self.assertIn("limit=100&offset=0", client.paths[0])
        self.assertIn("limit=100&offset=100", client.paths[1])

    def test_request_retries_transient_get_failure(self):
        class FakeResponse:
            status_code = 200
            content = b"{}"
            text = "{}"

            def json(self):
                return {"ok": True}

        class FakeSession:
            def __init__(self):
                self.calls = 0
                self.headers = {}

            def request(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise requests.ConnectionError("reset")
                return FakeResponse()

        client = RedmineClient("http://redmine.example")
        fake_session = FakeSession()
        client.session = fake_session
        with patch("time.sleep"):
            self.assertEqual(client._request("GET", "/projects.json"), {"ok": True})
        self.assertEqual(fake_session.calls, 2)

    def test_request_does_not_retry_project_file_creation(self):
        class FakeSession:
            def __init__(self):
                self.calls = 0
                self.headers = {}

            def request(self, *args, **kwargs):
                self.calls += 1
                raise requests.ConnectionError("reset")

        client = RedmineClient("http://redmine.example")
        fake_session = FakeSession()
        client.session = fake_session
        with self.assertRaises(Exception):
            client._request("POST", "/projects/dp5x/files.json", json={})
        self.assertEqual(fake_session.calls, 1)


if __name__ == "__main__":
    unittest.main()
