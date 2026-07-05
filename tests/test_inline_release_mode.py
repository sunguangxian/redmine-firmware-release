import unittest

from release_tool.release_page import (
    ReleaseForm,
    build_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    parse_inline_ref,
    parse_inline_releases,
    replace_inline_release_block,
)
from release_tool.wiki_config import parse_release_wiki_config
from release_tool.wiki_templates import build_config_template


class InlineReleaseModeTest(unittest.TestCase):
    def test_config_defaults_to_inline_when_field_missing(self):
        text = """
<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
```
<!-- RELEASE_CONFIG_END -->
"""
        config = parse_release_wiki_config(text)
        self.assertIsNotNone(config)
        self.assertEqual(config.release_detail_mode, "inline")

    def test_default_template_uses_inline_mode(self):
        template = build_config_template("single_list", "dp580")
        self.assertIn("release_detail_mode: inline", template)
        self.assertNotIn("release_page_prefix:", template)

    def test_inline_ref_round_trip(self):
        ref = inline_ref("Release_Notes", "V1.2.3")
        self.assertEqual(parse_inline_ref(ref), ("Release_Notes", "V1.2.3"))

    def test_replace_and_parse_inline_block(self):
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )
        block = build_inline_release_block(form, 12, [], source_page="Changelog")
        text = replace_inline_release_block("# Release Notes\n", "V1.2.3", block)
        self.assertIn("RELEASE_INLINE_BEGIN:V1.2.3", text)
        self.assertIn("[[Changelog]]", text)
        self.assertIn("修复问题", extract_inline_release_block(text, "V1.2.3"))
        rows = parse_inline_releases(text, "Release_Notes")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], "V1.2.3")
        self.assertEqual(rows[0]["product_line"], "常规版本 (5X)")


if __name__ == "__main__":
    unittest.main()
