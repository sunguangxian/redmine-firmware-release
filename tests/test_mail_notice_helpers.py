import unittest

from release_tool.config_store import MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL
from release_tool.email_sender import EmailSendError
from release_tool.mail_notice_helpers import validate_notice_fields


class MailNoticeHelpersTest(unittest.TestCase):
    def test_validate_notice_fields_returns_scope_and_recipients(self):
        scope, to_addrs, cc_addrs = validate_notice_fields(
            MAIL_SCOPE_EXTERNAL,
            "a@example.com; b@example.com",
            "c@example.com",
            "版本发布",
            "请查看版本说明",
        )

        self.assertEqual(scope, MAIL_SCOPE_EXTERNAL)
        self.assertEqual(to_addrs, ["a@example.com", "b@example.com"])
        self.assertEqual(cc_addrs, ["c@example.com"])

    def test_validate_notice_fields_defaults_scope_to_internal(self):
        scope, _to_addrs, _cc_addrs = validate_notice_fields(
            "",
            "a@example.com",
            "",
            "版本发布",
            "正文",
        )

        self.assertEqual(scope, MAIL_SCOPE_INTERNAL)

    def test_validate_notice_fields_normalizes_scope_error_to_email_error(self):
        with self.assertRaisesRegex(EmailSendError, "邮件类型只能是 internal 或 external"):
            validate_notice_fields("bad", "a@example.com", "", "主题", "正文")

    def test_validate_notice_fields_requires_recipient(self):
        with self.assertRaisesRegex(EmailSendError, "请填写或选择至少一个收件人"):
            validate_notice_fields(MAIL_SCOPE_INTERNAL, "", "", "主题", "正文")

    def test_validate_notice_fields_requires_subject(self):
        with self.assertRaisesRegex(EmailSendError, "请先生成或填写邮件主题"):
            validate_notice_fields(MAIL_SCOPE_INTERNAL, "a@example.com", "", "", "正文")

    def test_validate_notice_fields_requires_body(self):
        with self.assertRaisesRegex(EmailSendError, "请先生成或填写邮件正文"):
            validate_notice_fields(MAIL_SCOPE_INTERNAL, "a@example.com", "", "主题", "")


if __name__ == "__main__":
    unittest.main()
