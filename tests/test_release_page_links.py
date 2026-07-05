import unittest

from release_tool.release_page import (
    ReleaseForm,
    build_inline_release_block,
    build_release_markdown,
    project_path,
    version_or_roadmap_link,
)


class ReleasePageLinksTest(unittest.TestCase):
    def _form(self):
        return ReleaseForm(
            project_id="demo project",
            proj_tag="DEMO",
            version_name="V1.0.0",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )

    def test_project_path_quotes_project_identifier(self):
        self.assertEqual(project_path("demo project", "/files"), "/projects/demo%20project/files")
        self.assertEqual(project_path("demo/project", "roadmap"), "/projects/demo%2Fproject/roadmap")

    def test_version_or_roadmap_link_uses_version_when_available(self):
        self.assertEqual(version_or_roadmap_link("demo project", 12), "/versions/12")
        self.assertEqual(version_or_roadmap_link("demo project", None), "/projects/demo%20project/roadmap")

    def test_build_release_markdown_quotes_project_file_link(self):
        text = build_release_markdown(self._form(), None, [], main_page="Release_Main")

        self.assertIn("[项目文件](/projects/demo%20project/files)", text)
        self.assertIn("[版本 V1.0.0](/projects/demo%20project/roadmap)", text)
        self.assertIn("[[Release_Main|← 返回 Release Notes]]", text)

    def test_build_inline_release_block_quotes_project_file_link(self):
        text = build_inline_release_block(self._form(), None, [], block_id="V1.0.0", container_page="Release Main")

        self.assertIn("[项目文件](/projects/demo%20project/files)", text)
        self.assertIn("[版本 V1.0.0](/projects/demo%20project/roadmap)", text)
        self.assertNotIn("导航：", text)


if __name__ == "__main__":
    unittest.main()
