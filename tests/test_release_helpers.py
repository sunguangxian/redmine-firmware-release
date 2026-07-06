import unittest
from unittest.mock import Mock, patch

from release_tool.release_helpers import (
    RECENT_RELEASE_LIMIT,
    invalidate_release_rows,
    list_release_rows,
    validate_release_preflight,
)


class ReleaseHelpersTest(unittest.TestCase):
    def tearDown(self):
        invalidate_release_rows()

    def test_validate_release_preflight_accepts_valid_input(self):
        validate_release_preflight(
            project_id="demo",
            version_name="V1.0.0",
            release_date="2026-07-05",
            commit="abc123",
            changelog_items=["修复问题"],
        )

    def test_validate_release_preflight_requires_project(self):
        with self.assertRaisesRegex(ValueError, "请选择项目"):
            validate_release_preflight("", "V1", "2026-07-05", "abc", ["item"])

    def test_validate_release_preflight_requires_valid_date(self):
        with self.assertRaisesRegex(ValueError, "发布日期格式必须是 YYYY-MM-DD"):
            validate_release_preflight("demo", "V1", "2026/07/05", "abc", ["item"])

    def test_validate_release_preflight_requires_changelog(self):
        with self.assertRaisesRegex(ValueError, "请填写至少一条变更说明"):
            validate_release_preflight("demo", "V1", "2026-07-05", "abc", [])

    def test_list_release_rows_filters_and_limits(self):
        releases = [
            {"wiki_title": "A", "product_line": "5X"},
            {"wiki_title": "B", "product_line": "Record"},
            {"wiki_title": "C", "product_line": "5X"},
        ]
        publisher = Mock()
        publisher.list_releases.return_value = releases

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher):
            rows = list_release_rows(Mock(), "demo", "5X")

        self.assertEqual([item["wiki_title"] for item in rows], ["A", "C"])
        publisher.list_releases.assert_called_once_with("demo")

    def test_list_release_rows_does_not_limit_filtered_category(self):
        releases = [
            {"wiki_title": str(index), "product_line": "FM100B_V12"}
            for index in range(RECENT_RELEASE_LIMIT + 10)
        ]
        publisher = Mock()
        publisher.list_releases.return_value = releases

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher):
            rows = list_release_rows(Mock(), "demo", "FM100B_V12")

        self.assertEqual(len(rows), RECENT_RELEASE_LIMIT + 10)

    def test_list_release_rows_limits_recent_count(self):
        releases = [{"wiki_title": str(index), "product_line": ""} for index in range(RECENT_RELEASE_LIMIT + 5)]
        publisher = Mock()
        publisher.list_releases.return_value = releases

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher):
            rows = list_release_rows(Mock(), "demo")

        self.assertEqual(len(rows), RECENT_RELEASE_LIMIT)

    def test_list_release_rows_uses_cache_when_enabled(self):
        client = Mock()
        client.base_url = "http://redmine.local"
        publisher = Mock()
        publisher.list_releases.return_value = [{"wiki_title": "A", "product_line": ""}]

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher), patch(
            "release_tool.release_helpers.time.monotonic", side_effect=[100.0, 101.0]
        ):
            first = list_release_rows(client, "demo", use_cache=True)
            second = list_release_rows(client, "demo", use_cache=True)

        self.assertEqual(first, second)
        publisher.list_releases.assert_called_once_with("demo")

    def test_list_release_rows_refreshes_after_cache_expired(self):
        client = Mock()
        client.base_url = "http://redmine.local"
        publisher = Mock()
        publisher.list_releases.side_effect = [
            [{"wiki_title": "A", "product_line": ""}],
            [{"wiki_title": "B", "product_line": ""}],
        ]

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher), patch(
            "release_tool.release_helpers.time.monotonic", side_effect=[100.0, 200.0]
        ), patch.dict("os.environ", {"RELEASE_TOOL_RELEASE_CACHE_TTL": "30"}, clear=False):
            first = list_release_rows(client, "demo", use_cache=True)
            second = list_release_rows(client, "demo", use_cache=True)

        self.assertEqual(first[0]["wiki_title"], "A")
        self.assertEqual(second[0]["wiki_title"], "B")
        self.assertEqual(publisher.list_releases.call_count, 2)

    def test_invalidate_release_rows_refreshes_project_cache(self):
        client = Mock()
        client.base_url = "http://redmine.local"
        publisher = Mock()
        publisher.list_releases.side_effect = [
            [{"wiki_title": "A", "product_line": ""}],
            [{"wiki_title": "B", "product_line": ""}],
        ]

        with patch("release_tool.release_helpers.ReleasePublisher", return_value=publisher), patch(
            "release_tool.release_helpers.time.monotonic", side_effect=[100.0, 101.0]
        ):
            first = list_release_rows(client, "demo", use_cache=True)
            invalidate_release_rows("demo")
            second = list_release_rows(client, "demo", use_cache=True)

        self.assertEqual(first[0]["wiki_title"], "A")
        self.assertEqual(second[0]["wiki_title"], "B")
        self.assertEqual(publisher.list_releases.call_count, 2)


if __name__ == "__main__":
    unittest.main()
