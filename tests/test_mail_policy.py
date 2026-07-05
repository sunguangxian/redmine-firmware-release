import unittest
from unittest.mock import patch

from release_tool.config_store import MAIL_SCOPE_INTERNAL
from release_tool.mail_policy import contacts_for_scope


class MailPolicyTest(unittest.TestCase):
    def test_internal_contacts_keep_to_cc_separated(self):
        session = {"user_key": "redmine|alice"}
        with patch("release_tool.mail_policy.get_internal_contact_settings") as global_contacts, patch(
            "release_tool.mail_policy.get_user_internal_email_settings"
        ) as user_contacts:
            global_contacts.return_value = {
                "contacts": ["global-to@example.com", "global-cc@example.com"],
                "contacts_to": ["global-to@example.com"],
                "contacts_cc": ["global-cc@example.com"],
            }
            user_contacts.return_value = {
                "contacts_to": ["user-to@example.com"],
                "contacts_cc": ["user-cc@example.com"],
                "contact_templates": [],
            }

            result = contacts_for_scope(session, MAIL_SCOPE_INTERNAL)

        self.assertEqual(result["contacts_to"], ["global-to@example.com", "user-to@example.com"])
        self.assertEqual(result["contacts_cc"], ["global-cc@example.com", "user-cc@example.com"])


if __name__ == "__main__":
    unittest.main()
