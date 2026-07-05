import unittest
from unittest.mock import Mock, patch

from release_tool.config_store import MAIL_SCOPE_INTERNAL
from release_tool.email_sender import EmailSendError
from release_tool.mail_delivery_helpers import (
    build_notice_body,
    send_release_notice,
    validate_notice_preflight,
)


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

        title, body = build_notice_body(
            client,
            "demo",
            "Release_Notes#V1.0.0",
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
    @patch("release_tool.mail_delivery_helpers.send_release_email")
    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_send_release_notice_records_success(self, server, user_cfg, contacts, sender, history):
        server.return_value = _server()
        user_cfg.return_value = _user()
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}
        client = Mock()
        client.base_url = "http://redmine.local"

        message = send_release_notice(
            session={"user_key": "u1", "user_login": "admin"},
            client=client,
            project_id="demo",
            wiki_title="Release_Notes#V1.0.0",
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

    @patch("release_tool.mail_delivery_helpers.record_mail_send")
    @patch("release_tool.mail_delivery_helpers.send_release_email")
    @patch("release_tool.mail_delivery_helpers.get_internal_contact_settings")
    @patch("release_tool.mail_delivery_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_delivery_helpers.get_email_server_settings")
    def test_send_release_notice_records_failure(self, server, user_cfg, contacts, sender, history):
        server.return_value = _server()
        user_cfg.return_value = _user()
        contacts.return_value = {"contacts_to": [], "contacts_cc": []}
        sender.side_effect = EmailSendError("failed")
        client = Mock()
        client.base_url = "http://redmine.local"

        with self.assertRaisesRegex(EmailSendError, "failed"):
            send_release_notice(
                session={"user_key": "u1", "user_login": "admin"},
                client=client,
                project_id="demo",
                wiki_title="Release_Notes#V1.0.0",
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


if __name__ == "__main__":
    unittest.main()
