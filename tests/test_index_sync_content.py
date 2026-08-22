import unittest

from release_tool.index_sync import IndexSync


class IndexSyncContentTest(unittest.TestCase):
    def test_section_replacement_preserves_following_manual_sections(self):
        sync = object.__new__(IndexSync)
        current = (
            "# Release Notes\n\n"
            "## Product Lines\n\n"
            "old generated content\n\n"
            "## 人工维护说明\n\n"
            "keep me\n"
        )

        updated = sync._replace_generated_region(
            current,
            "## Product Lines\n\nnew generated content",
            "Product Lines",
        )

        self.assertIn("new generated content", updated)
        self.assertNotIn("old generated content", updated)
        self.assertIn("## 人工维护说明\n\nkeep me", updated)


if __name__ == "__main__":
    unittest.main()
