import unittest

from fake_redmine import FakeRedmineClient
from release_tool.release_mode_converter import ReleaseModeConverter
from release_tool.release_page import build_inline_release_block, build_release_markdown

from test_release_flow_fake_redmine import INLINE_CONFIG, PAGE_CONFIG, form


SINGLE_INLINE_CONFIG = """# Release Tool Config

<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
release_page_prefix: Release_PT7200D_FW_
```
<!-- RELEASE_CONFIG_END -->
"""


class ReleaseModeConverterTest(unittest.TestCase):
    def test_page_to_inline_copies_releases_and_keeps_old_pages(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", PAGE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_page("Release_Notes_Regular", "# 甯歌鐗堟湰\n")
        client.seed_page(
            "Release_Notes_Regular_List",
            "# Regular\n\n"
            "[[Release_Notes|back to Release Notes]]\n\n"
            "--------------\n\n"
            "{{>toc}}\n\n"
            "- [[Release_Regular_FW_V1_0_0|V1.0.0 (2026-07-05)]] - old summary\n",
        )
        client.seed_version("V1.0.0", 1)
        release_text = build_release_markdown(
            form("V1.0.0"),
            1,
            [{"filename": "fw.bin", "description": "", "url": "/files/fw.bin"}],
            main_page="Release_Notes",
        )
        client.seed_page("Release_Regular_FW_V1_0_0", release_text, parent_title="Release_Notes_Regular")

        preview = ReleaseModeConverter(client, "dp5x").preview("inline")
        self.assertEqual(preview["current_mode"], "page")
        self.assertEqual(preview["target_mode"], "inline")
        self.assertEqual(preview["release_count"], 1)
        self.assertIn("Release_Notes_Regular", preview["pages_to_write"])
        self.assertIn("Release_Notes_Regular_List", preview["pages_to_delete"])

        result = ReleaseModeConverter(client, "dp5x").convert("inline")
        self.assertTrue(result["config_updated"])
        self.assertEqual(result["converted_count"], 1)
        self.assertEqual(result["deleted_pages"], ["Release_Notes_Regular_List", "Release_Regular_FW_V1_0_0"])
        self.assertIn("release_detail_mode: inline", client.pages["Release_Tool_Config"]["text"])
        self.assertIn("list_page: Release_Notes_Regular", client.pages["Release_Tool_Config"]["text"])
        self.assertNotIn("Release_Regular_FW_V1_0_0", client.pages)
        self.assertNotIn("Release_Notes_Regular_List", client.pages)
        container_text = client.pages["Release_Notes_Regular"]["text"]
        self.assertIn("<!-- RELEASE_INLINE_BEGIN:Release_Regular_FW_V1_0_0 -->", container_text)
        self.assertIn("## version:V1.0.0 (2026-07-05)", container_text)
        self.assertIn("fw.bin", container_text)
        self.assertNotIn("[[Release_Notes|back to Release Notes]]", container_text)
        self.assertNotIn("[[Release_Regular_FW_V1_0_0|V1.0.0 (2026-07-05)]] - old summary", container_text)
        self.assertEqual(client.versions[0]["wiki_page_title"], "Release_Notes_Regular")

    def test_inline_to_page_copies_blocks_and_keeps_inline_container(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_version("V1.0.0", 1)
        block = build_inline_release_block(
            form("V1.0.0"),
            1,
            [{"filename": "fw.bin", "description": "", "url": "/files/fw.bin"}],
            block_id="Release_Regular_FW_V1_0_0",
            display_version="V1.0.0",
            container_page="Release_Notes_Regular",
        )
        client.seed_page("Release_Notes_Regular", "# 甯歌鐗堟湰\n\n" + block, parent_title="Release_Notes")

        preview = ReleaseModeConverter(client, "dp5x").preview("page")
        self.assertEqual(preview["current_mode"], "inline")
        self.assertIn("Release_Regular_FW_V1_0_0", preview["pages_to_write"])

        result = ReleaseModeConverter(client, "dp5x").convert("page")
        self.assertTrue(result["config_updated"])
        self.assertEqual(result["converted_count"], 1)
        self.assertIn("release_detail_mode: page", client.pages["Release_Tool_Config"]["text"])
        self.assertIn("Release_Regular_FW_V1_0_0", client.pages)
        self.assertIn("RELEASE_INLINE_BEGIN:Release_Regular_FW_V1_0_0", client.pages["Release_Notes_Regular"]["text"])
        page_text = client.pages["Release_Regular_FW_V1_0_0"]["text"]
        self.assertIn("# [V1.0.0](/versions/1)", page_text)
        self.assertIn("fw.bin", page_text)
        self.assertEqual(client.versions[0]["wiki_page_title"], "Release_Regular_FW_V1_0_0")

    def test_inline_config_with_page_content_can_still_convert_to_inline(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_page("Release_Notes_Regular", "# 甯歌鐗堟湰\n")
        client.seed_version("V1.0.0", 1)
        release_text = build_release_markdown(
            form("V1.0.0"),
            1,
            [{"filename": "fw.bin", "description": "", "url": "/files/fw.bin"}],
            main_page="Release_Notes",
        )
        client.seed_page("Release_Regular_FW_V1_0_0", release_text, parent_title="Release_Notes_Regular")

        preview = ReleaseModeConverter(client, "dp5x").preview("inline")
        self.assertEqual(preview["current_mode"], "inline")
        self.assertEqual(preview["source_mode"], "page")
        self.assertEqual(preview["target_mode"], "inline")
        self.assertEqual(preview["release_count"], 1)

        result = ReleaseModeConverter(client, "dp5x").convert("inline")
        self.assertFalse(result["config_updated"])
        self.assertEqual(result["converted_count"], 1)
        self.assertIn("Release_Regular_FW_V1_0_0", result["deleted_pages"])
        self.assertNotIn("Release_Regular_FW_V1_0_0", client.pages)
        self.assertIn("release_detail_mode: inline", client.pages["Release_Tool_Config"]["text"])
        self.assertIn("<!-- RELEASE_INLINE_BEGIN:Release_Regular_FW_V1_0_0 -->", client.pages["Release_Notes_Regular"]["text"])
        self.assertIn("fw.bin", client.pages["Release_Notes_Regular"]["text"])

    def test_inline_cleanup_removes_leftover_page_navigation(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_version("V1.0.0", 1)
        block = build_inline_release_block(
            form("V1.0.0"),
            1,
            [{"filename": "fw.bin", "description": "", "url": "/files/fw.bin"}],
            block_id="Release_Regular_FW_V1_0_0",
            display_version="V1.0.0",
            container_page="Release_Notes_Regular",
        )
        client.seed_page(
            "Release_Notes_Regular",
            "# Regular\n\n"
            "[[Release_Notes|back to Release Notes]]\n\n"
            "--------------\n\n"
            "{{>toc}}\n\n"
            "## Version List\n\n"
            "{{>toc}}\n\n"
            "- [[Release_Regular_FW_V1_0_0|V1.0.0 (2026-07-05)]] - old summary\n\n"
            + block,
            parent_title="Release_Notes",
        )

        result = ReleaseModeConverter(client, "dp5x").convert("inline")

        self.assertEqual(result["converted_count"], 1)
        text = client.pages["Release_Notes_Regular"]["text"]
        self.assertNotIn("[[Release_Notes|back to Release Notes]]", text)
        self.assertNotIn("## Version List", text)
        self.assertNotIn("[[Release_Regular_FW_V1_0_0|V1.0.0 (2026-07-05)]] - old summary", text)
        self.assertEqual(text.count("{{>toc}}"), 1)
        self.assertIn("<!-- RELEASE_INLINE_BEGIN:Release_Regular_FW_V1_0_0 -->", text)
        self.assertNotIn("**Commit:** abc123\n\n--------------", text)

    def test_inline_cleanup_deletes_stale_list_page(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        client.seed_page("Release_Notes", "# Release Notes\n")
        client.seed_page("Release_Notes_Regular_List", "# old list\n")
        client.seed_page("Release_Regular_FW_V1_0_0", "# old detail\n")
        client.seed_version("V1.0.0", 1)
        block = build_inline_release_block(
            form("V1.0.0"),
            1,
            [],
            block_id="Release_Regular_FW_V1_0_0",
            display_version="V1.0.0",
            container_page="Release_Notes_Regular",
        )
        client.seed_page("Release_Notes_Regular", "# Regular\n\n" + block, parent_title="Release_Notes")

        preview = ReleaseModeConverter(client, "dp5x").preview("inline")
        self.assertEqual(preview["pages_to_delete"], ["Release_Notes_Regular_List", "Release_Regular_FW_V1_0_0"])

        result = ReleaseModeConverter(client, "dp5x").convert("inline")

        self.assertEqual(result["deleted_pages"], ["Release_Notes_Regular_List", "Release_Regular_FW_V1_0_0"])
        self.assertNotIn("Release_Notes_Regular_List", client.pages)
        self.assertNotIn("Release_Regular_FW_V1_0_0", client.pages)

    def test_single_inline_cleanup_deletes_old_release_detail_pages(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", SINGLE_INLINE_CONFIG)
        client.seed_version("V5.3.8.10", 1)
        block = build_inline_release_block(
            form("V5.3.8.10"),
            1,
            [],
            block_id="Release_PT7200D_FW_V5_3_8_10",
            display_version="V5.3.8.10",
            container_page="Release_Notes",
        )
        client.seed_page("Release_Notes", "# Release Notes\n\n" + block)
        client.seed_page("Release_PT7200D_FW_V5_3_8_10", "# old detail\n", parent_title="Release_Notes")

        preview = ReleaseModeConverter(client, "pt7200d").preview("inline")
        self.assertEqual(preview["pages_to_delete"], ["Release_PT7200D_FW_V5_3_8_10"])

        result = ReleaseModeConverter(client, "pt7200d").convert("inline")

        self.assertEqual(result["deleted_pages"], ["Release_PT7200D_FW_V5_3_8_10"])
        self.assertNotIn("Release_PT7200D_FW_V5_3_8_10", client.pages)
        self.assertIn("## version:V5.3.8.10 (2026-07-05)", client.pages["Release_Notes"]["text"])

    def test_inline_with_legacy_list_page_moves_blocks_to_hub(self):
        client = FakeRedmineClient()
        legacy_inline_config = PAGE_CONFIG.replace("release_detail_mode: page", "release_detail_mode: inline")
        client.seed_page("Release_Tool_Config", legacy_inline_config)
        client.seed_page(
            "Release_Notes",
            "# Release Notes\n\n"
            "> Version lists are maintained by the release tool in the `*_List` pages.\n\n"
            "{{>toc}}\n\n"
            "{{>toc}}\n\n"
            "## Product Lines\n\n"
            "- [[Release_Notes_Regular_List|old list]]\n\n"
            "<!-- RELEASE_SYNC_BEGIN -->\n"
            "## Product Lines\n\n"
            "- [[Release_Notes_Regular|new list]]\n"
            "<!-- RELEASE_SYNC_END -->\n",
        )
        client.seed_page(
            "Release_Notes_Regular",
            "# Regular\n\n"
            "[[Release_Notes|back to Release Notes]]\n\n"
            "--------------\n\n"
            "{{>toc}}\n\n"
            "## Version List\n\n"
            "{{include(Release_Notes_Regular_List)}}\n",
            parent_title="Release_Notes",
        )
        client.seed_version("V1.0.0", 1)
        block = build_inline_release_block(
            form("V1.0.0"),
            1,
            [{"filename": "fw.bin", "description": "", "url": "/files/fw.bin"}],
            block_id="Release_Regular_FW_V1_0_0",
            display_version="V1.0.0",
            container_page="Release_Notes_Regular_List",
        )
        client.seed_page("Release_Notes_Regular_List", "{{>toc}}\n\n" + block, parent_title="Release_Notes_Regular")

        preview = ReleaseModeConverter(client, "dp5x").preview("inline")
        self.assertTrue(preview["config_will_change"])
        self.assertEqual(preview["pages_to_write"], ["Release_Notes_Regular"])
        self.assertEqual(preview["pages_to_delete"], ["Release_Notes_Regular_List"])

        result = ReleaseModeConverter(client, "dp5x").convert("inline")

        self.assertTrue(result["config_updated"])
        self.assertEqual(result["converted_count"], 1)
        self.assertEqual(result["deleted_pages"], ["Release_Notes_Regular_List"])
        self.assertNotIn("Release_Notes_Regular_List", client.pages)
        self.assertIn("list_page: Release_Notes_Regular", client.pages["Release_Tool_Config"]["text"])
        hub_text = client.pages["Release_Notes_Regular"]["text"]
        self.assertIn("<!-- RELEASE_INLINE_BEGIN:Release_Regular_FW_V1_0_0 -->", hub_text)
        self.assertNotIn("include(Release_Notes_Regular_List)", hub_text)
        self.assertNotIn("## Version List", hub_text)
        self.assertEqual(hub_text.count("{{>toc}}"), 1)
        main_text = client.pages["Release_Notes"]["text"]
        self.assertNotIn("Release_Notes_Regular_List", main_text)
        self.assertEqual(main_text.count("{{>toc}}"), 1)
        self.assertEqual(client.versions[0]["wiki_page_title"], "Release_Notes_Regular")

    def test_invalid_target_mode_is_rejected(self):
        client = FakeRedmineClient()
        client.seed_page("Release_Tool_Config", INLINE_CONFIG)
        with self.assertRaises(Exception):
            ReleaseModeConverter(client, "dp5x").preview("auto")


if __name__ == "__main__":
    unittest.main()

