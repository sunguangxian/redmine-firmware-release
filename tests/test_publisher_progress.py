import unittest
from unittest.mock import patch

from release_tool.publisher import ReleasePublisher
from release_tool.release_page import ReleaseForm


class FakeProfile:
    mode = "single_list"
    categories = []
    main_page = "Release_Notes"
    release_page_prefix = ""
    release_detail_mode = "page"


class FakeIndexSync:
    def sync_after_publish(self, title, markdown):
        self.title = title
        self.markdown = markdown


class FakeClient:
    base_url = "http://redmine.example"

    def list_versions(self, project_id):
        return [{"id": 1, "name": "V1.0.0"}]

    def get_wiki_page(self, project_id, title):
        return None

    def put_wiki_page(self, project_id, title, text, comment):
        self.wiki_written = True

    def update_version(self, version_id, **fields):
        self.version_updated = True

    def list_project_files(self, project_id):
        return []


class PublisherProgressTest(unittest.TestCase):
    def test_publish_reports_stage_progress(self):
        form = ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name="V1.0.0",
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
            files=[],
        )
        events = []

        with patch("release_tool.publisher.ensure_release_structure_ready") as ensure_ready:
            ensure_ready.return_value = (FakeIndexSync(), FakeProfile())
            title = ReleasePublisher(FakeClient()).publish(
                form,
                logs=[],
                progress=lambda stage, status: events.append((stage, status)),
            )

        self.assertEqual(title, "Release_DP580_FW_V1_0_0")
        self.assertIn(("file", "skipped"), events)
        self.assertIn(("release", "running"), events)
        self.assertIn(("release", "success"), events)
        self.assertIn(("wiki", "success"), events)
        self.assertIn(("index", "success"), events)


if __name__ == "__main__":
    unittest.main()
