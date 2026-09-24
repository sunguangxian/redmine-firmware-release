import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from release_tool.dependencies import _current_client, _current_session
from release_tool.email_sender import EmailSendError
from release_tool.release_ops_api import register_release_ops_routes
from release_tool.release_page import inline_ref


def _session(project_id="demo", is_admin=True):
    return {
        "connected": True,
        "is_admin": is_admin,
        "user_key": "u1",
        "user_login": "admin",
        "projects": [{"identifier": project_id}],
    }


class ReleaseNoticeResendApiTest(unittest.TestCase):
    def _client(self, session):
        app = FastAPI()
        register_release_ops_routes(app)
        app.dependency_overrides[_current_session] = lambda: session
        app.dependency_overrides[_current_client] = lambda: Mock()
        return TestClient(app)

    def test_resend_attaches_published_firmware_and_ignores_uploads(self):
        published = [("fw.bin", "SHA256: abc", b"firmware")]
        with self._client(_session()) as http, patch(
            "release_tool.release_ops_api._validate_notice_preflight",
            return_value=("internal", ["a@example.com"], ["b@example.com"]),
        ), patch(
            "release_tool.release_ops_api.load_published_mail_attachments",
            return_value=published,
        ) as loader, patch(
            "release_tool.release_ops_api._read_mail_files",
            side_effect=AssertionError("补发不应读取本次上传的文件"),
        ), patch(
            "release_tool.release_ops_api._send_release_notice",
            return_value="内网邮件已发送",
        ) as sender, patch("release_tool.release_ops_api.record_mail_send") as history:
            response = http.post(
                "/api/releases/notice/send",
                data={
                    "project_id": "demo",
                    "wiki_title": inline_ref("Release_Notes", "V1.0.0"),
                    "version_name": "V1.0.0",
                    "mail_to": "a@example.com",
                    "mail_subject": "主题",
                    "mail_body": "正文",
                    "send_type": "resend",
                },
                files=[("files", ("extra.bin", b"ignore-me", "application/octet-stream"))],
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("补发邮件将附带已发布固件 1 个", response.json()["logs"])
        loader.assert_called_once()
        self.assertEqual(loader.call_args.args[1:], ("demo", inline_ref("Release_Notes", "V1.0.0")))
        self.assertEqual(sender.call_args.kwargs["file_rows"], published)
        self.assertEqual(sender.call_args.kwargs["send_type"], "resend")
        history.assert_not_called()

    def test_resend_records_failure_when_published_firmware_cannot_be_loaded(self):
        title = inline_ref("Release_Notes", "V1.0.0")
        with self._client(_session()) as http, patch(
            "release_tool.release_ops_api._validate_notice_preflight",
            return_value=("internal", ["a@example.com"], []),
        ), patch(
            "release_tool.release_ops_api.load_published_mail_attachments",
            side_effect=EmailSendError("该版本没有可随邮件发送的固件附件。未发送邮件。"),
        ), patch(
            "release_tool.release_ops_api._send_release_notice",
            side_effect=AssertionError("附件不齐时不应发送邮件"),
        ), patch("release_tool.release_ops_api.record_mail_send") as history:
            response = http.post(
                "/api/releases/notice/send",
                data={
                    "project_id": "demo",
                    "wiki_title": title,
                    "version_name": "V1.0.0",
                    "mail_to": "a@example.com",
                    "mail_subject": "主题",
                    "mail_body": "正文",
                    "send_type": "resend",
                },
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("没有可随邮件发送的固件附件", response.json()["detail"])
        history.assert_called_once()
        self.assertEqual(history.call_args.kwargs["status"], "failed")
        self.assertEqual(history.call_args.kwargs["send_type"], "resend")
        self.assertEqual(history.call_args.kwargs["wiki_title"], "Release_Notes")
        self.assertEqual(history.call_args.kwargs["version_name"], "V1.0.0")
        self.assertEqual(history.call_args.kwargs["attachment_count"], 0)

    def test_retry_still_uses_uploaded_files(self):
        captured = {}

        def fake_send(**kwargs):
            content = kwargs["file_rows"][0][2]
            content.seek(0)
            captured["name"] = kwargs["file_rows"][0][0]
            captured["data"] = content.read()
            captured["send_type"] = kwargs["send_type"]
            return "已发送"

        with self._client(_session()) as http, patch(
            "release_tool.release_ops_api._validate_notice_preflight",
            return_value=("internal", ["a@example.com"], []),
        ), patch(
            "release_tool.release_ops_api.load_published_mail_attachments",
            side_effect=AssertionError("立即重发不应下载已发布固件"),
        ), patch(
            "release_tool.release_ops_api._send_release_notice",
            side_effect=fake_send,
        ):
            response = http.post(
                "/api/releases/notice/send",
                data={
                    "project_id": "demo",
                    "wiki_title": "Release_Demo",
                    "version_name": "V1.0.0",
                    "mail_to": "a@example.com",
                    "mail_subject": "主题",
                    "mail_body": "正文",
                    "send_type": "retry",
                },
                files=[("files", ("fw.bin", b"firmware", "application/octet-stream"))],
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["send_type"], "retry")
        self.assertEqual(captured["name"], "fw.bin")
        self.assertEqual(captured["data"], b"firmware")

    def test_resend_requires_project_access(self):
        with self._client(_session(project_id="other", is_admin=False)) as http, patch(
            "release_tool.release_ops_api.load_published_mail_attachments",
            side_effect=AssertionError("无权项目不应读取固件"),
        ):
            response = http.post(
                "/api/releases/notice/send",
                data={
                    "project_id": "demo",
                    "wiki_title": "Release_Demo",
                    "mail_to": "a@example.com",
                    "mail_subject": "主题",
                    "mail_body": "正文",
                    "send_type": "resend",
                },
            )

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
