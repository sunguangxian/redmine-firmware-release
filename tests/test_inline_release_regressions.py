import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from release_tool import mail_history, release_publish_history
from release_tool.index_sync import IndexSync
from release_tool.mail_history import _wiki_title_candidates as mail_title_candidates
from release_tool.publisher import ReleasePublisher
from release_tool.release_page import (
    ReleaseForm,
    build_inline_release_block,
    delete_inline_release_block,
    extract_inline_release_block,
    inline_ref,
    parse_inline_releases,
    replace_inline_release_block,
)
from release_tool.release_publish_history import _wiki_title_candidates as publish_title_candidates


class InlineReleaseRegressionTest(unittest.TestCase):
    def _form(self, version="V1.0.0"):
        return ReleaseForm(
            project_id="dp580",
            proj_tag="DP580",
            version_name=version,
            release_date="2026-07-05",
            commit="abc123",
            product_line="常规版本 (5X)",
            changelog_items=["修复问题"],
        )

    def test_inline_block_id_can_differ_from_display_version(self):
        block = build_inline_release_block(self._form("V1.0.0"), 1, [], block_id="Release_DM181_FW_V1_0_0_20260705", display_version="V1.0.0")
        text = replace_inline_release_block("# Release Notes\n", "Release_DM181_FW_V1_0_0_20260705", block)
        rows = parse_inline_releases(text, "Release_Notes_DM181")
        self.assertEqual(rows[0]["title"], inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0_20260705"))
        self.assertEqual(rows[0]["version"], "V1.0.0")
        self.assertEqual(rows[0]["block_id"], "Release_DM181_FW_V1_0_0_20260705")

    def test_rename_inline_version_deletes_old_block(self):
        old_block = build_inline_release_block(self._form("V1.0.0"), 1, [], block_id="V1.0.0")
        text = replace_inline_release_block("# Release Notes\n", "V1.0.0", old_block)
        text = delete_inline_release_block(text, "V1.0.0")
        new_block = build_inline_release_block(self._form("V1.0.1"), 1, [], block_id="V1.0.1")
        text = replace_inline_release_block(text, "V1.0.1", new_block)
        self.assertEqual(extract_inline_release_block(text, "V1.0.0"), "")
        self.assertIn("V1.0.1", extract_inline_release_block(text, "V1.0.1"))

    def test_unique_migration_block_id_is_preserved_on_edit(self):
        publisher = ReleasePublisher(None)
        self.assertEqual(
            publisher._next_block_id(
                "Release_DM181_FW_V1_0_0_20260705",
                "V1.0.0",
                "V1.0.1",
                True,
            ),
            "Release_DM181_FW_V1_0_0_20260705",
        )
        self.assertEqual(publisher._next_block_id("V1.0.0", "V1.0.0", "V1.0.1", True), "V1.0.1")

    def test_index_links_use_container_page_for_inline_items(self):
        sync = IndexSync.__new__(IndexSync)
        lines = sync._format_release_lines(
            [
                {
                    "page": inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0"),
                    "container_page": "Release_Notes_DM181",
                    "ver": "V1.0.0",
                    "date": "2026-07-05",
                    "summary": "修复问题",
                }
            ],
        )
        self.assertIn("[[Release_Notes_DM181|V1.0.0 (2026-07-05)]]", lines)
        self.assertNotIn("INLINE::", lines)

    def test_inline_history_title_candidates_include_container_page(self):
        title = inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0")
        self.assertEqual(mail_title_candidates(title), [title, "Release_Notes_DM181"])
        self.assertEqual(publish_title_candidates(title), [title, "Release_Notes_DM181"])

    def test_inline_history_needs_version_filter_for_container_records(self):
        title = inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0")
        candidates = publish_title_candidates(title)
        self.assertIn("Release_Notes_DM181", candidates)
        self.assertIn(title, candidates)
        # 查询接口会额外带 version_name，避免同一承载页下多个版本的历史混在一起。
        self.assertEqual(len(candidates), 2)

    def test_inline_history_queries_filter_container_records_by_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = f"{tmpdir}/history.db"

            @contextmanager
            def temp_db():
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                    conn.commit()
                finally:
                    conn.close()

            with patch("release_tool.mail_history.db", temp_db), patch("release_tool.release_publish_history.db", temp_db):
                first_publish_id = release_publish_history.create_publish_history(
                    project_id="dp580",
                    version_name="V1.0.0",
                    action="发布",
                )
                release_publish_history.update_publish_history(first_publish_id, wiki_title="Release_Notes_DM181")
                second_publish_id = release_publish_history.create_publish_history(
                    project_id="dp580",
                    version_name="V1.0.1",
                    action="发布",
                )
                release_publish_history.update_publish_history(second_publish_id, wiki_title="Release_Notes_DM181")
                mail_history.record_mail_send(
                    project_id="dp580",
                    wiki_title="Release_Notes_DM181",
                    version_name="V1.0.0",
                    scope="internal",
                    subject="V1.0.0",
                    to_addrs=["a@example.com"],
                    cc_addrs=[],
                    attachment_count=0,
                    sender_user="tester",
                    status="success",
                )
                mail_history.record_mail_send(
                    project_id="dp580",
                    wiki_title="Release_Notes_DM181",
                    version_name="V1.0.1",
                    scope="internal",
                    subject="V1.0.1",
                    to_addrs=["b@example.com"],
                    cc_addrs=[],
                    attachment_count=0,
                    sender_user="tester",
                    status="success",
                )

                inline_title = inline_ref("Release_Notes_DM181", "Release_DM181_FW_V1_0_0")
                publish_rows = release_publish_history.list_publish_history(
                    project_id="dp580",
                    wiki_title=inline_title,
                    version_name="V1.0.0",
                )
                mail_rows = mail_history.list_mail_history(
                    project_id="dp580",
                    wiki_title=inline_title,
                    version_name="V1.0.0",
                )

            self.assertEqual([row["version_name"] for row in publish_rows], ["V1.0.0"])
            self.assertEqual([row["subject"] for row in mail_rows], ["V1.0.0"])

            conn = sqlite3.connect(db_file)
            try:
                index_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
            finally:
                conn.close()
            self.assertIn("idx_release_publish_history_version_recent_lookup", index_names)
            self.assertIn("idx_mail_send_history_version_recent_lookup", index_names)


if __name__ == "__main__":
    unittest.main()
