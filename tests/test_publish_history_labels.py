import unittest

from release_tool.release_publish_history import _decode_row


class PublishHistoryLabelsTest(unittest.TestCase):
    def test_decode_row_adds_status_labels_and_summary(self):
        item = _decode_row(
            {
                "id": 1,
                "project_id": "dp580",
                "wiki_title": "Release_DP580_FW_V1_0_0",
                "version_name": "V1.0.0",
                "action": "发布新版本",
                "release_status": "success",
                "file_status": "skipped",
                "wiki_status": "success",
                "index_status": "failed",
                "mail_status": "skipped",
                "error_message": "",
                "logs": "[]",
                "form_payload": "{}",
                "created_at": "2026-07-05 10:00:00",
                "updated_at": "2026-07-05 10:00:00",
            }
        )
        self.assertEqual(item["release_status_label"], "成功")
        self.assertEqual(item["file_status_label"], "跳过")
        self.assertIn("版本索引:失败", item["status_summary"])
        self.assertTrue(item["can_rebuild_index"])
        self.assertFalse(item["can_continue"])

    def test_decode_row_allows_continue_without_local_files(self):
        item = _decode_row(
            {
                "id": 2,
                "project_id": "dp580",
                "wiki_title": "Release_DP580_FW_V1_0_0",
                "version_name": "V1.0.0",
                "action": "发布新版本",
                "release_status": "success",
                "file_status": "skipped",
                "wiki_status": "failed",
                "index_status": "pending",
                "mail_status": "skipped",
                "error_message": "",
                "logs": "[]",
                "form_payload": '{"has_files": false}',
                "created_at": "2026-07-05 10:00:00",
                "updated_at": "2026-07-05 10:00:00",
            }
        )
        self.assertTrue(item["can_continue"])
        self.assertIn({"action": "continue", "label": "继续发布"}, item["recover_actions"])


if __name__ == "__main__":
    unittest.main()
