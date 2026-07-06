import unittest

from release_tool.release_page import (
    ReleaseForm,
    build_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    parse_inline_ref,
    parse_inline_releases,
    normalize_inline_release_page,
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
        self.assertIn("{{>toc}}", text)
        self.assertIn("RELEASE_INLINE_BEGIN:V1.2.3", text)
        self.assertIn("## version:V1.2.3 (2026-07-05)", text)
        self.assertIn("[版本 V1.2.3](/versions/12)", text)
        self.assertNotIn("## version:V1.2.3 (2026-07-05)\n\n[版本 V1.2.3](/versions/12)", text)
        self.assertNotIn("Release DP580 FW V1.2.3", text)
        self.assertIn("**变更说明**", text)
        self.assertIn("**固件文件**", text)
        self.assertNotIn("迁移来源", text)
        self.assertNotIn("### 变更说明", text)
        self.assertNotIn("### 固件文件", text)
        self.assertNotIn("**产品线:**", text)
        self.assertNotIn("**Commit:** abc123\n\n--------------", text)
        self.assertNotIn("## 版本列表", text)
        self.assertNotIn("[[Changelog]]", text)
        self.assertIn("修复问题", extract_inline_release_block(text, "V1.2.3"))
        rows = parse_inline_releases(text, "Release_Notes")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], "V1.2.3")
        self.assertEqual(rows[0]["product_line"], "")

    def test_inline_container_uses_toc_navigation(self):
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )
        block = build_inline_release_block(form, 12, [], container_page="Release_Notes")
        text = replace_inline_release_block("# Release Notes\n", "V1.2.3", block)
        self.assertIn("{{>toc}}", text)
        self.assertIn("## version:V1.2.3 (2026-07-05)", text)
        self.assertIn("[版本 V1.2.3](/versions/12)", text)
        self.assertNotIn("## version:V1.2.3 (2026-07-05)\n\n[版本 V1.2.3](/versions/12)", text)
        self.assertNotIn("## 版本列表", text)

    def test_existing_toc_is_split_from_previous_paragraph(self):
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="甯歌鐗堟湰 (5X)",
            changelog_items=["淇闂"],
        )
        block = build_inline_release_block(form, 12, [], container_page="Release_Notes")
        text = replace_inline_release_block("# Release Notes\n\nsummary\n{{>toc}}\n", "V1.2.3", block)

        self.assertIn("summary\n\n{{>toc}}\n\n<!-- RELEASE_INLINE_BEGIN:V1.2.3 -->", text)

    def test_inline_blocks_are_sorted_by_date_and_semantic_version(self):
        def block(version: str, date: str) -> str:
            form = ReleaseForm(
                project_id="dp580",
                proj_tag="DP580",
                version_name=version,
                release_date=date,
                commit="abc123",
                product_line="常规版本 (5X)",
                changelog_items=[f"change {version}"],
            )
            return build_inline_release_block(form, 12, [], block_id=f"Release_DP580_FW_{version.replace('.', '_')}")

        page = "# Release Notes\n\n{{>toc}}\n\n" + "\n\n".join(
            [
                block("V5.3.6.1", "2023-07-04"),
                block("V5.3.6.10", "2023-08-11"),
                block("V5.3.6.2", "2023-08-11"),
                block("V5.3.7.55", "2026-07-03"),
            ]
        )

        text = replace_inline_release_block(page, "missing", block("V5.3.6.3", "2023-07-05"))

        headings = [line for line in text.splitlines() if line.startswith("## version:")]
        self.assertEqual(
            headings,
            [
                "## version:V5.3.7.55 (2026-07-03)",
                "## version:V5.3.6.10 (2023-08-11)",
                "## version:V5.3.6.2 (2023-08-11)",
                "## version:V5.3.6.3 (2023-07-05)",
                "## version:V5.3.6.1 (2023-07-04)",
            ],
        )
        self.assertEqual(text.count("\n--------------\n"), 4)
        self.assertNotIn("**Commit:** abc123\n\n--------------", text)

    def test_inline_blocks_are_sorted_within_category_sections(self):
        def block(version: str, date: str) -> str:
            form = ReleaseForm(
                project_id="dp580",
                proj_tag="DP580",
                version_name=version,
                release_date=date,
                commit="abc123",
                product_line="Series",
                changelog_items=[f"change {version}"],
            )
            return build_inline_release_block(form, 12, [], block_id=version.replace(".", "_")).replace(
                "## version:", "### version:", 1
            )

        page = (
            "# Release Notes\n\n{{>toc}}\n\n"
            "## Series A\n\n"
            + block("V1.0.0.1", "2024-01-01")
            + "\n\n"
            + block("V1.0.0.2", "2024-02-01")
            + "\n\n"
            "## Series B\n\n"
            + block("V2.0.0.1", "2026-01-01")
        )

        text = normalize_inline_release_page(page)
        self.assertLess(text.index("## Series A"), text.index("### version:V1.0.0.2"))
        self.assertLess(text.index("### version:V1.0.0.2"), text.index("### version:V1.0.0.1"))
        self.assertLess(text.index("### version:V1.0.0.1"), text.index("## Series B"))
        self.assertLess(text.index("## Series B"), text.index("### version:V2.0.0.1"))

    def test_new_inline_block_is_inserted_into_matching_category_section(self):
        def block(version: str, date: str) -> str:
            form = ReleaseForm(
                project_id="dp580",
                proj_tag="DP580",
                version_name=version,
                release_date=date,
                commit="abc123",
                product_line="Series",
                changelog_items=[f"change {version}"],
            )
            return build_inline_release_block(form, 12, [], block_id=version.replace(".", "_")).replace(
                "## version:", "### version:", 1
            )

        page = (
            "# Release Notes\n\n{{>toc}}\n\n"
            "## Series A V1.0.0.X\n\n"
            + block("V1.0.0.1", "2024-01-01")
            + "\n\n"
            "## Series B V2.0.0.X\n\n"
            + block("V2.0.0.1", "2026-01-01")
        )

        text = replace_inline_release_block(page, "missing", block("V1.0.0.3", "2024-03-01"))

        self.assertLess(text.index("## Series A V1.0.0.X"), text.index("### version:V1.0.0.3"))
        self.assertLess(text.index("### version:V1.0.0.3"), text.index("### version:V1.0.0.1"))
        self.assertLess(text.index("### version:V1.0.0.1"), text.index("## Series B V2.0.0.X"))

    def test_edited_inline_block_moves_to_matching_category_section(self):
        def block(version: str, date: str, block_id: str) -> str:
            form = ReleaseForm(
                project_id="dp580",
                proj_tag="DP580",
                version_name=version,
                release_date=date,
                commit="abc123",
                product_line="Series",
                changelog_items=[f"change {version}"],
            )
            return build_inline_release_block(form, 12, [], block_id=block_id).replace("## version:", "### version:", 1)

        page = (
            "# Release Notes\n\n{{>toc}}\n\n"
            "## Series A V1.0.0.X\n\n"
            + block("V1.0.0.1", "2024-01-01", "stable_block")
            + "\n\n"
            "## Series B V2.0.0.X\n\n"
            + block("V2.0.0.1", "2026-01-01", "V2_0_0_1")
        )

        text = replace_inline_release_block(page, "stable_block", block("V2.0.0.2", "2026-02-01", "stable_block"))

        self.assertLess(text.index("## Series A V1.0.0.X"), text.index("## Series B V2.0.0.X"))
        self.assertLess(text.index("## Series B V2.0.0.X"), text.index("### version:V2.0.0.2"))
        self.assertLess(text.index("### version:V2.0.0.2"), text.index("### version:V2.0.0.1"))

    def test_inline_heading_version_link_without_blank_line_is_removed(self):
        old_block = """# Release Notes

{{>toc}}

<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->
## version:V1.0.0 (2024-01-02)
[版本 V1.0.0](/versions/10)

**日期:** 2024-01-02
**Commit:** abc123

**变更说明**

1. old change

**固件文件**

下载: [版本 V1.0.0](/versions/10) | [项目文件](/projects/dp580/files)
<!-- RELEASE_INLINE_END:V1.0.0 -->
"""
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )
        block = build_inline_release_block(form, 12, [])
        text = replace_inline_release_block(old_block, "V1.2.3", block)

        self.assertNotIn("## version:V1.0.0 (2024-01-02)\n[版本 V1.0.0](/versions/10)", text)
        self.assertIn("下载: [版本 V1.0.0](/versions/10)", text)

    def test_existing_inline_blocks_are_normalized_for_toc(self):
        old_block = """# Release Notes

{{>toc}}

<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->
## Release DP580 FW V1.0.0

### 变更说明

1. old change

### 固件文件

下载: [版本 V1.0.0](/versions/10) | [项目文件](/projects/dp580/files)

| 文件名 | 说明 |
|--------|------|
| （无） | |

### 迁移来源

- [[Changelog]]
<!-- RELEASE_INLINE_END:V1.0.0 -->
"""
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )
        block = build_inline_release_block(form, 12, [])
        text = replace_inline_release_block(old_block, "V1.2.3", block)

        self.assertIn("## version:V1.0.0", text)
        self.assertIn("[版本 V1.0.0](/versions/10)", text)
        self.assertNotIn("## version:V1.0.0\n\n[版本 V1.0.0](/versions/10)", text)
        self.assertNotIn("## Release DP580 FW V1.0.0", text)
        self.assertIn("**变更说明**", text)
        self.assertIn("**固件文件**", text)
        self.assertNotIn("迁移来源", text)
        self.assertNotIn("### 变更说明", text)
        self.assertNotIn("### 固件文件", text)
        self.assertNotIn("### 迁移来源", text)

    def test_existing_linked_inline_titles_are_simplified(self):
        old_block = """# Release Notes

{{>toc}}

<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->
## [Release DP580 FW V1.0.0](/versions/10)

**变更说明**

1. old change

**固件文件**

下载: [版本 V1.0.0](/versions/10) | [项目文件](/projects/dp580/files)

| 文件名 | 说明 |
|--------|------|
| （无） | |
<!-- RELEASE_INLINE_END:V1.0.0 -->
"""
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )
        block = build_inline_release_block(form, 12, [])
        text = replace_inline_release_block(old_block, "V1.2.3", block)

        self.assertIn("## version:V1.0.0", text)
        self.assertIn("[版本 V1.0.0](/versions/10)", text)
        self.assertNotIn("Release DP580 FW V1.0.0", text)


if __name__ == "__main__":
    unittest.main()
