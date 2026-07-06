import unittest

from release_tool.legacy_changelog_migrator import LegacyChangelogMigrator


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


if __name__ == "__main__":
    unittest.main()
