import unittest

from fake_redmine import FakeRedmineClient
from release_tool.legacy_changelog_migrator import LegacyChangelogMigrator, LegacyRelease, LegacySourcePage
from release_tool.wiki_config import parse_release_wiki_config


class FakeClient:
    def __init__(self, config_text=""):
        self.config_text = config_text

    def get_wiki_page(self, project_id, title, **kwargs):
        if not self.config_text:
            return None
        return {"text": self.config_text}


class FakeMigrator(LegacyChangelogMigrator):
    def __init__(self, mode="auto", config_text=""):
        self.release_detail_mode = self._normalize_detail_mode(mode)
        self.client = FakeClient(config_text)
        self.project_id = "dp580"


class MigrationDetailModeTest(unittest.TestCase):
    def test_normalize_mode(self):
        migrator = LegacyChangelogMigrator(FakeClient(), "dp580")
        self.assertEqual(migrator._normalize_detail_mode("inline"), "inline")
        self.assertEqual(migrator._normalize_detail_mode("page"), "page")
        self.assertEqual(migrator._normalize_detail_mode("bad"), "auto")
        self.assertEqual(migrator._normalize_detail_mode(""), "auto")

    def test_explicit_mode_has_priority(self):
        self.assertEqual(FakeMigrator("page")._selected_detail_mode(), "page")
        self.assertEqual(FakeMigrator("inline")._selected_detail_mode(), "inline")

    def test_auto_uses_existing_config(self):
        config = """
<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
release_detail_mode: page
release_page_prefix: Release_DP580_FW_
```
<!-- RELEASE_CONFIG_END -->
"""
        self.assertEqual(FakeMigrator("auto", config)._selected_detail_mode(), "page")

    def test_auto_defaults_to_inline_without_config(self):
        self.assertEqual(FakeMigrator("auto")._selected_detail_mode(), "inline")

    def test_non_version_section_heading_stops_previous_release_body(self):
        migrator = LegacyChangelogMigrator(FakeClient(), "dp580")
        text = """# Changelog for Model

## Series A

## version:V1.0.0 (2024-01-02)

- commit: abc123

1. first change

## Series B

## version:V2.0.0 (2024-02-03)

- commit: def456

1. second change
"""
        releases = migrator._parse_releases("Changelog_for_Model", "Model", text, {})

        self.assertEqual([release.version for release in releases], ["V1.0.0", "V2.0.0"])
        self.assertEqual(releases[0].changelog_items, ["first change"])
        self.assertNotIn("Series B", "\n".join(releases[0].changelog_items))

    def test_multi_model_page_migration_uses_model_pages_without_extra_list_pages(self):
        client = FakeRedmineClient()
        migrator = LegacyChangelogMigrator(client, "demo", release_detail_mode="page")
        categories = [
            {"key": "F864", "title": "F864"},
            {"key": "F864X", "title": "F864X"},
        ]

        migrator._save_release_tool_config(categories, single_list=False, detail_mode="page")
        migrator._create_release_structure(categories, single_list=False, detail_mode="page")

        config = parse_release_wiki_config(client.pages["Release_Tool_Config"]["text"])
        self.assertIsNotNone(config)
        self.assertTrue(all(item.list_page == item.hub_page for item in config.categories))
        self.assertIn("Release_Notes_F864", client.pages)
        self.assertIn("Release_Notes_F864X", client.pages)
        self.assertNotIn("Release_Notes_F864_List", client.pages)
        self.assertNotIn("Release_Notes_F864X_List", client.pages)
        self.assertNotIn("include(", client.pages["Release_Notes_F864"]["text"])

    def test_preview_reports_standard_multi_model_inline_layout(self):
        client = FakeRedmineClient()
        releases = [
            LegacyRelease("F864", "F864", "Changelog_F864", "V1.0", "2026-01-01", "a", ["change"]),
            LegacyRelease("F864X", "F864X", "Changelog_F864X", "V2.0", "2026-01-02", "b", ["change"]),
        ]
        sources = [
            LegacySourcePage("Changelog_F864", "F864", 1, 0, 0),
            LegacySourcePage("Changelog_F864X", "F864X", 1, 0, 0),
        ]
        migrator = LegacyChangelogMigrator(client, "demo", release_detail_mode="inline")
        migrator.scan = lambda: (releases, sources, [])

        preview = migrator.preview()

        self.assertEqual(preview["project_structure"], "multi_model")
        self.assertEqual(preview["project_structure_label"], "多型号项目")
        self.assertEqual(preview["release_detail_mode_label"], "所有版本一个页面")
        self.assertEqual(preview["model_pages"], ["Release_Notes_F864", "Release_Notes_F864X"])
        self.assertEqual(
            preview["index_pages_to_write"],
            ["Release_Notes", "Release_Notes_F864", "Release_Notes_F864X"],
        )
        self.assertEqual(preview["release_pages_to_create"], 2)


if __name__ == "__main__":
    unittest.main()
