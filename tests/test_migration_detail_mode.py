import unittest

from release_tool.inline_release_patch import normalize_migration_detail_mode, selected_migration_detail_mode


class FakeClient:
    def __init__(self, config_text=""):
        self.config_text = config_text

    def get_wiki_page(self, project_id, title, **kwargs):
        if not self.config_text:
            return None
        return {"text": self.config_text}


class FakeMigrator:
    project_id = "dp580"

    def __init__(self, mode="auto", config_text=""):
        self.release_detail_mode = mode
        self.client = FakeClient(config_text)


class MigrationDetailModeTest(unittest.TestCase):
    def test_normalize_mode(self):
        self.assertEqual(normalize_migration_detail_mode("inline"), "inline")
        self.assertEqual(normalize_migration_detail_mode("page"), "page")
        self.assertEqual(normalize_migration_detail_mode("bad"), "auto")
        self.assertEqual(normalize_migration_detail_mode(""), "auto")

    def test_explicit_mode_has_priority(self):
        self.assertEqual(selected_migration_detail_mode(FakeMigrator("page")), "page")
        self.assertEqual(selected_migration_detail_mode(FakeMigrator("inline")), "inline")

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
        self.assertEqual(selected_migration_detail_mode(FakeMigrator("auto", config)), "page")

    def test_auto_defaults_to_inline_without_config(self):
        self.assertEqual(selected_migration_detail_mode(FakeMigrator("auto")), "inline")


if __name__ == "__main__":
    unittest.main()
