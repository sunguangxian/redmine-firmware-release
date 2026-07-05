import unittest

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


if __name__ == "__main__":
    unittest.main()
