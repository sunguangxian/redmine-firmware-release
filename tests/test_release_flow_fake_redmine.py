import unittest

from fake_redmine import FakeRedmineClient
from release_tool.index_sync import IndexSync
from release_tool.publisher import ReleasePublisher
from release_tool.release_page import ReleaseForm, build_inline_release_block, build_release_markdown, inline_ref
from release_tool.release_planner import ReleasePlanner


INLINE_CONFIG = """# Release Tool Config

<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: multi_list
main_page: Release_Notes
release_detail_mode: inline
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular
```
<!-- RELEASE_CONFIG_END -->
"""

PAGE_CONFIG = """# Release Tool Config

<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: multi_list
main_page: Release_Notes
release_detail_mode: page
release_page_prefix: Release_{category}_FW_
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular_List
```
<!-- RELEASE_CONFIG_END -->
"""


def form(version="V1.0.0", *, wiki_title=None, files=None, replace=False):
    return ReleaseForm(
        project_id="dp5x",
        proj_tag="DP5X",
        version_name=version,
        release_date="2026-07-05",
        commit="abc123",
        product_line="常规版本 (5X)",
        changelog_items=["修复问题"],
        files=files or [],
        wiki_title=wiki_title,
        replace_attachments=replace,
    )


class ReleaseFlowFakeRedmineTest(unittest.TestCase):
    def seed_inline(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_page("Release_Notes_Regular", "# 常规版本\n\n## 版本列表\n")
        client.seed_version("V1.0.0", 1)
        return client

    def seed_page(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", PAGE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_page("Release_Notes_Regular", "# 常规版本\n")
        client.seed_page("Release_Notes_Regular_List", "# 常规版本列表\n")
        client.seed_version("V1.0.0", 1)
        return client

    def test_inline_new_publish_writes_container_block(self):
        client = self.seed_inline()
        title = ReleasePublisher(client).publish(form())
        self.assertEqual(title, inline_ref("Release_Notes_Regular", "V1.0.0"))
        container_text = client.pages["Release_Notes_Regular"]["text"]
        self.assertIn("<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->", container_text)
        self.assertNotIn("## 版本列表", container_text)
        self.assertNotIn("**产品线:**", container_text)
        self.assertIn("[[Release_Notes_Regular|V1.0.0 (2026-07-05)]]", client.pages["Release_Notes"]["text"])

        rows = ReleasePublisher(client).list_releases("dp5x")
        self.assertEqual(rows[0]["product_line"], "常规版本 (5X)")

    def test_inline_edit_can_rename_display_version_block(self):
        client = self.seed_inline()
        block = build_inline_release_block(form("V1.0.0"), 1, [], block_id="V1.0.0")
        client.seed_page("Release_Notes_Regular", "# 常规版本\n\n" + block)
        title = ReleasePublisher(client).publish(form("V1.0.1", wiki_title=inline_ref("Release_Notes_Regular", "V1.0.0")))
        self.assertEqual(title, inline_ref("Release_Notes_Regular", "V1.0.1"))
        text = client.pages["Release_Notes_Regular"]["text"]
        self.assertNotIn("RELEASE_INLINE_BEGIN:V1.0.0", text)
        self.assertIn("RELEASE_INLINE_BEGIN:V1.0.1", text)

    def test_page_publish_uses_configured_release_title(self):
        client = self.seed_page()
        title = ReleasePublisher(client).publish(form())
        self.assertEqual(title, "Release_Regular_FW_V1_0_0")
        self.assertIn("# [V1.0.0](/versions/", client.pages[title]["text"])
        self.assertNotIn("**产品线:**", client.pages[title]["text"])
        self.assertIn("[[Release_Regular_FW_V1_0_0|V1.0.0 (2026-07-05)]]", client.pages["Release_Notes_Regular_List"]["text"])
        self.assertNotIn("## 版本列表", client.pages["Release_Notes_Regular_List"]["text"])

        rows = ReleasePublisher(client).list_releases("dp5x")
        self.assertEqual(rows[0]["product_line"], "常规版本 (5X)")

    def test_planner_reports_page_and_inline_targets(self):
        inline_client = self.seed_inline()
        inline_plan = ReleasePlanner(inline_client).build_plan(form())
        self.assertEqual(inline_plan["mode"], "inline")
        self.assertEqual(inline_plan["container_page"], "Release_Notes_Regular")
        self.assertEqual(inline_plan["block_id"], "V1.0.0")

        page_client = self.seed_page()
        page_plan = ReleasePlanner(page_client).build_plan(form())
        self.assertEqual(page_plan["mode"], "page")
        self.assertEqual(page_plan["target_page"], "Release_Regular_FW_V1_0_0")

    def test_page_edit_attachment_append_and_replace(self):
        client = self.seed_page()
        old_text = build_release_markdown(
            form("V1.0.0"),
            1,
            [{"filename": "old.bin", "description": "", "url": "/files/old.bin"}],
        )
        client.seed_page("Release_Regular_FW_V1_0_0", old_text, parent_title="Release_Notes_Regular")

        ReleasePublisher(client).publish(
            form("V1.0.0", wiki_title="Release_Regular_FW_V1_0_0", files=[("new.bin", "", b"123")], replace=False)
        )
        appended = client.pages["Release_Regular_FW_V1_0_0"]["text"]
        self.assertIn("old.bin", appended)
        self.assertIn("new.bin", appended)

        ReleasePublisher(client).publish(
            form("V1.0.0", wiki_title="Release_Regular_FW_V1_0_0", files=[("only.bin", "", b"456")], replace=True)
        )
        replaced = client.pages["Release_Regular_FW_V1_0_0"]["text"]
        self.assertNotIn("old.bin", replaced)
        self.assertIn("only.bin", replaced)

    def test_inline_refresh_counts_existing_blocks_only(self):
        client = self.seed_inline()
        ReleasePublisher(client).publish(form())
        self.assertEqual(IndexSync(client, "dp5x").refresh_all(), 1)


if __name__ == "__main__":
    unittest.main()
