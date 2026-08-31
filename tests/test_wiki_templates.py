import unittest

from release_tool.wiki_config import parse_release_wiki_config
from release_tool.wiki_templates import TEMPLATE_CHOICES, build_config_template


class WikiTemplatesTest(unittest.TestCase):
    def test_templates_expose_the_four_supported_model_and_version_layouts(self):
        self.assertEqual(
            TEMPLATE_CHOICES,
            [
                ("单型号 / 所有版本一个页面", "single_list"),
                ("单型号 / 每个版本独立页面", "single_list_page"),
                ("多型号 / 每个型号所有版本一个页面", "multi_list_direct"),
                ("多型号 / 每个版本独立页面", "multi_list_page"),
            ],
        )

    def test_new_multi_model_templates_do_not_create_extra_list_pages(self):
        for template_key, detail_mode in (
            ("multi_list_direct", "inline"),
            ("multi_list_page", "page"),
        ):
            config = parse_release_wiki_config(build_config_template(template_key, "demo"))

            self.assertIsNotNone(config)
            self.assertEqual(config.mode, "multi_list")
            self.assertEqual(config.release_detail_mode, detail_mode)
            self.assertTrue(config.categories)
            self.assertTrue(all(item.list_page == item.hub_page for item in config.categories))

    def test_legacy_include_template_keys_generate_the_canonical_structure(self):
        for template_key in ("multi_list_include", "multi_list_include_page"):
            config = parse_release_wiki_config(build_config_template(template_key, "demo"))

            self.assertIsNotNone(config)
            self.assertTrue(all(item.list_page == item.hub_page for item in config.categories))


if __name__ == "__main__":
    unittest.main()
