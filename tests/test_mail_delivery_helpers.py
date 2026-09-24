import unittest
from unittest.mock import Mock, patch

from release_tool.config_store import MAIL_SCOPE_INTERNAL
from release_tool.email_sender import EmailSendError
from release_tool.mail_delivery_helpers import (
    build_notice_body,
    load_published_mail_attachments,
    send_release_notice,
    validate_notice_preflight,
)
from release_tool.redmine_api import RedmineError
from release_tool.release_page import inline_ref


def _server(sender="sender@example.com"):
    return {
        "smtp_host": "mail.example.com",
        "smtp_port": 25,
        "smtp_from": sender,
        "use_tls": False,
    }


def _user(sender="user@example.com"):
    return {
        "smtp_user": "user",
        "smtp_" + "password": "secret",
        "smtp_from": sender,
        "contacts_to": ["to@example.com"],
        "contacts_cc": ["cc@example.com"],
    }


class MailDeliveryHelpersTest(unittest.TestCase):
    def test_build_notice_body_replaces_links(self):
        client = Mock()
        client.base_url = "http://redmine.local/"
        wiki_title = inline_ref("Release_Notes", "V1.0.0")

        title, body = build_notice_body(
            client,
            "demo",
            wiki_title,
            "Wiki={{wiki_url}}\nFiles={{files_url}}",
        )

        self.assertEqual(title, "Release_Notes")
        self.assertIn("http://redmine.local/projects/demo/wiki/Release_Notes", body)
        self.assertIn("http://redmine.local/projects/demo/files", body)

    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_validate_notice_preflight_returns_addresses(self, server, user_cfg, contacts):
        server.return_value = _server()
        user_cfg.return_value = _user()
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}

        scope, to_addrs, cc_addrs = validate_notice_preflight(
            {"user_key": "u1"},
            MAIL_SCOPE_INTERNAL,
            "a@example.com",
            "b@example.com",
            "主题",
            "正文",
        )

        self.assertEqual(scope, MAIL_SCOPE_INTERNAL)
        self.assertEqual(to_addrs, ["a@example.com"])
        self.assertEqual(cc_addrs, ["b@example.com"])

    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_validate_notice_preflight_requires_configured_sender(self, server, user_cfg, contacts):
        server.return_value = _server(sender="")
        user_cfg.return_value = _user(sender="")
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}

        with self.assertRaisesRegex(EmailSendError, "默认发件人"):
            validate_notice_preflight(
                {"user_key": "u1"},
                MAIL_SCOPE_INTERNAL,
                "a@example.com",
                "",
                "主题",
                "正文",
            )

    @patch("release_tool.mail_delivery_helpers.record_mail_send")
    @patch("release_tool.mail_delivery_helpers.save_new_contacts_for_scope")
    @patch("release_tool.mail_delivery_helpers.send_release_email")
    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_send_release_notice_records_success(self, server, user_cfg, contacts, sender, save_contacts, history):
        server.return_value = _server()
        user_cfg.return_value = _user()
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}
        client = Mock()
        client.base_url = "http://redmine.local"
        wiki_title = inline_ref("Release_Notes", "V1.0.0")

        message = send_release_notice(
            session={"user_key": "u1", "user_login": "admin"},
            client=client,
            project_id="demo",
            wiki_title=wiki_title,
            version_name="V1.0.0",
            file_rows=[("fw.bin", "", b"123")],
            mail_scope=MAIL_SCOPE_INTERNAL,
            mail_to=["a@example.com"],
            mail_cc=["b@example.com"],
            mail_subject="主题",
            mail_body="正文 {{wiki_url}}",
            send_type="publish",
        )

        self.assertIn("邮件已发送", message)
        sender.assert_called_once()
        history.assert_called_once()
        self.assertEqual(history.call_args.kwargs["status"], "success")
        self.assertEqual(history.call_args.kwargs["wiki_title"], "Release_Notes")
        save_contacts.assert_called_once_with(
            {"user_key": "u1", "user_login": "admin"},
            MAIL_SCOPE_INTERNAL,
            ["a@example.com"],
            ["b@example.com"],
        )

    @patch("release_tool.mail_delivery_helpers.record_mail_send")
    @patch("release_tool.mail_delivery_helpers.save_new_contacts_for_scope")
    @patch("release_tool.mail_delivery_helpers.send_release_email")
    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_send_release_notice_records_failure(self, server, user_cfg, contacts, sender, save_contacts, history):
        server.return_value = _server()
        user_cfg.return_value = _user()
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}
        sender.side_effect = EmailSendError("failed")
        client = Mock()
        client.base_url = "http://redmine.local"
        wiki_title = inline_ref("Release_Notes", "V1.0.0")

        with self.assertRaisesRegex(EmailSendError, "failed"):
            send_release_notice(
                session={"user_key": "u1", "user_login": "admin"},
                client=client,
                project_id="demo",
                wiki_title=wiki_title,
                version_name="V1.0.0",
                file_rows=[],
                mail_scope=MAIL_SCOPE_INTERNAL,
                mail_to=["a@example.com"],
                mail_cc=[],
                mail_subject="主题",
                mail_body="正文",
                send_type="publish",
            )

        self.assertEqual(history.call_args.kwargs["status"], "failed")
        self.assertEqual(history.call_args.kwargs["error_message"], "failed")
        save_contacts.assert_not_called()


def _firmware_page(*rows: str) -> str:
    body = "\n".join(rows) or "| （无） | |"
    return "\n".join([
        "## 固件文件",
        "",
        "| 文件名 | 说明 |",
        "|--------|------|",
        body,
    ])


class PublishedMailAttachmentTest(unittest.TestCase):
    def _client(self, text: str, downloads=None):
        client = Mock()
        client.base_url = "http://redmine.local"
        client.get_wiki_page.return_value = {"text": text}
        client.download_content_url.side_effect = downloads or (lambda url: b"firmware-" + url.encode("utf-8"))
        return client

    def test_loads_every_published_firmware_file(self):
        client = self._client(_firmware_page(
            "| [fw.bin](/attachments/download/1/fw.bin) | SHA256: abc |",
            "| [boot.bin](http://redmine.local/attachments/download/2/boot.bin) | |",
        ))

        rows = load_published_mail_attachments(client, "demo", "Release_Demo")

        self.assertEqual([item[0] for item in rows], ["fw.bin", "boot.bin"])
        self.assertEqual(rows[0][2], b"firmware-/attachments/download/1/fw.bin")
        client.download_content_url.assert_any_call("/attachments/download/1/fw.bin")
        client.download_content_url.assert_any_call("/attachments/download/2/boot.bin")

    def test_inline_release_uses_only_the_selected_block(self):
        text = """
<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->
## 固件文件

| 文件名 | 说明 |
|--------|------|
| [a.bin](/attachments/download/1/a.bin) | |
<!-- RELEASE_INLINE_END:V1.0.0 -->
<!-- RELEASE_INLINE_BEGIN:V2.0.0 -->
## 固件文件

| 文件名 | 说明 |
|--------|------|
| [b.bin](/attachments/download/2/b.bin) | |
<!-- RELEASE_INLINE_END:V2.0.0 -->
"""
        client = self._client(text)
        title = inline_ref("Release_Notes", "V1.0.0")

        rows = load_published_mail_attachments(client, "demo", title)

        self.assertEqual([item[0] for item in rows], ["a.bin"])
        client.get_wiki_page.assert_called_once_with("demo", "Release_Notes")
        client.download_content_url.assert_called_once_with("/attachments/download/1/a.bin")

    def test_rejects_version_without_firmware(self):
        client = self._client("## 变更说明\n\n1. 修复问题\n")

        with self.assertRaisesRegex(EmailSendError, "没有可随邮件发送的固件附件"):
            load_published_mail_attachments(client, "demo", "Release_Demo")
        client.download_content_url.assert_not_called()

    def test_rejects_firmware_without_download_url(self):
        client = self._client(_firmware_page("| fw.bin | |"))

        with self.assertRaisesRegex(EmailSendError, "缺少下载地址：fw.bin"):
            load_published_mail_attachments(client, "demo", "Release_Demo")
        client.download_content_url.assert_not_called()

    def test_rejects_download_url_outside_redmine(self):
        client = self._client(_firmware_page("| [fw.bin](https://files.example/fw.bin) | |"))

        with self.assertRaisesRegex(EmailSendError, "不在当前 Redmine：fw.bin"):
            load_published_mail_attachments(client, "demo", "Release_Demo")
        client.download_content_url.assert_not_called()

    def test_rejects_empty_or_failed_download_without_partial_success(self):
        client = self._client(
            _firmware_page(
                "| [fw.bin](/attachments/download/1/fw.bin) | |",
                "| [boot.bin](/attachments/download/2/boot.bin) | |",
            ),
            downloads=lambda url: b"" if url.endswith("boot.bin") else b"ok",
        )

        with self.assertRaisesRegex(EmailSendError, "固件附件为空：boot.bin"):
            load_published_mail_attachments(client, "demo", "Release_Demo")

        client.download_content_url.side_effect = RedmineError("HTTP 404")
        with self.assertRaisesRegex(EmailSendError, "下载固件附件失败：fw.bin"):
            load_published_mail_attachments(client, "demo", "Release_Demo")

    def test_rejects_attachments_over_mail_limit(self):
        client = self._client(
            _firmware_page("| [fw.bin](/attachments/download/1/fw.bin) | |"),
            downloads=lambda url: b"12345",
        )

        with patch("release_tool.mail_delivery_helpers.MAX_MAIL_ATTACHMENT_BYTES", 4):
            with self.assertRaisesRegex(EmailSendError, "fw.bin 合计 5 B，最大 4 B"):
                load_published_mail_attachments(client, "demo", "Release_Demo")

    def test_missing_wiki_page_does_not_download(self):
        client = self._client("")
        client.get_wiki_page.return_value = None

        with self.assertRaisesRegex(EmailSendError, "未找到已发布版本"):
            load_published_mail_attachments(client, "demo", "Release_Demo")
        client.download_content_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
