import unittest
from unittest.mock import Mock

from release_tool.publisher import ReleasePublisher
from release_tool.redmine_api import RedmineError


class PublisherConflictTest(unittest.TestCase):
    def test_assert_wiki_unchanged_accepts_same_text(self):
        client = Mock()
        client.get_wiki_page.return_value = {"text": "old text"}
        logs = []

        ReleasePublisher(client)._assert_wiki_unchanged("demo", "Release_A", "old text", logs)

        self.assertIn("Wiki 冲突检测通过：Release_A", logs)

    def test_assert_wiki_unchanged_rejects_external_change(self):
        client = Mock()
        client.get_wiki_page.return_value = {"text": "changed text"}
        logs = []

        with self.assertRaisesRegex(RedmineError, "已被其他用户修改"):
            ReleasePublisher(client)._assert_wiki_unchanged("demo", "Release_A", "old text", logs)

        self.assertIn("Wiki 冲突检测失败：Release_A", logs)

    def test_assert_wiki_unchanged_detects_new_page_created_by_other_user(self):
        client = Mock()
        client.get_wiki_page.return_value = {"text": "created by someone else"}

        with self.assertRaisesRegex(RedmineError, "避免覆盖他人改动"):
            ReleasePublisher(client)._assert_wiki_unchanged("demo", "Release_New", "", [])


if __name__ == "__main__":
    unittest.main()
