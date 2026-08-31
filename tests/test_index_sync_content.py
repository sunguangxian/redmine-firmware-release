import unittest

from release_tool.index_sync import IndexSync, SYNC_BEGIN, SYNC_END


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
        self.assertEqual(updated.count(SYNC_BEGIN), 1)
        self.assertEqual(sync._replace_generated_region(updated, "## Product Lines\n\nnew generated content", "Product Lines"), updated)

    def test_version_list_replacement_is_marked_and_idempotent(self):
        sync = object.__new__(IndexSync)
        current = "# F864\n\n## 版本列表\n\n- old version\n"
        generated = "- [[Release_F864_FW_V2|V2 (2026-01-01)]] - new"

        updated = sync._replace_generated_region(current, generated, "版本列表")
        updated_again = sync._replace_generated_region(updated, generated, "版本列表")

        self.assertEqual(updated, updated_again)
        self.assertNotIn("old version", updated)
        self.assertEqual(updated.count("V2 (2026-01-01)"), 1)
        self.assertEqual(updated.count(SYNC_BEGIN), 1)

    def test_legacy_main_index_replaces_all_duplicate_model_sections_and_becomes_idempotent(self):
        sync = object.__new__(IndexSync)
        current = (
            "# Release Notes\n\nmanual introduction\n\n"
            "## Product Lines\n\n- old models\n\n"
            "## F864\n\n- old current links\n\n"
            "## F864\n\n- stale *_List links\n"
        )
        generated = "## Product Lines\n\n- new models\n\n## F864\n\n- current versions"

        updated = sync._replace_main_generated_region(current, generated)
        updated_again = sync._replace_main_generated_region(updated, generated)

        self.assertEqual(updated, updated_again)
        self.assertIn("manual introduction", updated)
        self.assertNotIn("old current links", updated)
        self.assertNotIn("stale *_List links", updated)
        self.assertEqual(updated.count("## F864"), 1)
        self.assertEqual(updated.count(SYNC_BEGIN), 1)
        self.assertEqual(updated.count(SYNC_END), 1)


if __name__ == "__main__":
    unittest.main()
