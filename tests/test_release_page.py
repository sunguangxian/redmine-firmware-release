import unittest

from release_tool.release_page import ReleaseForm, build_release_markdown, parse_release_files


class ReleasePageTest(unittest.TestCase):
    def test_build_release_markdown_uses_configured_main_page(self):
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.2.3",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复发布流程"],
            files=[],
        )
        markdown = build_release_markdown(form, None, [], main_page="DP580_Releases")
        self.assertIn("# [V1.2.3](/projects/dp580/roadmap)", markdown)
        self.assertNotIn("# Release DP580 FW V1.2.3", markdown)
        self.assertNotIn("**产品线:**", markdown)
        self.assertIn("[[DP580_Releases|← 返回 Release Notes]]", markdown)
        self.assertNotIn("[[Release_Notes|← 返回 Release Notes]]", markdown)

    def test_parse_release_files_reads_markdown_table_links(self):
        text = """
## 固件文件

| 文件名 | 说明 |
|--------|------|
| [firmware.bin](/attachments/download/1/firmware.bin) | SHA256: abc |
"""
        files = parse_release_files(text)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "firmware.bin")
        self.assertEqual(files[0]["url"], "/attachments/download/1/firmware.bin")
        self.assertEqual(files[0]["description"], "SHA256: abc")


if __name__ == "__main__":
    unittest.main()
