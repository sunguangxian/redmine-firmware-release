import unittest

from release_tool.inline_release_patch import _format_release_lines_inline_aware
from release_tool.release_page import (
    ReleaseForm,
    build_inline_release_block,
    delete_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    parse_inline_releases,
    replace_inline_release_block,
)


class InlineReleaseRegressionTest(unittest.TestCase):
    def _form(self, version="V1.0.0"):
        return ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name=version,
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )

    def test_inline_block_id_can_differ_from_display_version(self):
        block = build_inline_release_block(self._form("V1.0.0"), 1, [], block_id="Release_DM181_FW_V1_0_0_20260705", display_version="V1.0.0")
        text = replace_inline_release_block("# Release Notes\n", "Release_DM181_FW_V1_0_0_20260705", block)
        rows = parse_inline_releases(text, "Release_Notes_DM181")
        self.assertEqual(rows[0]["title"], inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0_20260705"))
        self.assertEqual(rows[0]["version"], "V1.0.0")
        self.assertEqual(rows[0]["block_id"], "Release_DM181_FW_V1_0_0_20260705")

    def test_rename_inline_version_deletes_old_block(self):
        old_block = build_inline_release_block(self._form("V1.0.0"), 1, [], block_id="V1.0.0")
        text = replace_inline_release_block("# Release Notes\n", "V1.0.0", old_block)
        text = delete_inline_release_block(text, "V1.0.0")
        new_block = build_inline_release_block(self._form("V1.0.1"), 1, [], block_id="V1.0.1")
        text = replace_inline_release_block(text, "V1.0.1", new_block)
        self.assertEqual(extract_inline_release_block(text, "V1.0.0"), "")
        self.assertIn("V1.0.1", extract_inline_release_block(text, "V1.0.1"))

    def test_index_links_use_container_page_for_inline_items(self):
        lines = _format_release_lines_inline_aware(
            None,
            [
                {
                    "page": inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0"),
                    "container_page": "Release_Notes_DM181",
                    "ver": "V1.0.0",
                    "date": "2026-07-05",
                    "summary": "修复问题",
                }
            ],
        )
        self.assertIn("[[Release_Notes_DM181|V1.0.0 (2026-07-05)]]", lines)
        self.assertNotIn("INLINE::", lines)


if __name__ == "__main__":
    unittest.main()
