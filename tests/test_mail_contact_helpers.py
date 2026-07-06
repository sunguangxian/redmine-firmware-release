import unittest
from unittest.mock import patch

from fastapi import HTTPException

from release_tool.config_store import MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL
from release_tool.mail_contact_helpers import (
    contact_people,
    contacts_for_scope,
    mail_scope_label,
    merge_contact_lists,
    normalize_mail_scope,
)


class MailContactHelpersTest(unittest.TestCase):
    def test_normalize_mail_scope_defaults_to_internal(self):
        self.assertEqual(normalize_mail_scope(""), MAIL_SCOPE_INTERNAL)
        self.assertEqual(normalize_mail_scope(None), MAIL_SCOPE_INTERNAL)

    def test_normalize_mail_scope_rejects_unknown_scope(self):
        with self.assertRaises(HTTPException) as ctx:
            normalize_mail_scope("bad")

        self.assertEqual(ctx.exception.status_code, 400)

    def test_mail_scope_label(self):
        self.assertEqual(mail_scope_label(MAIL_SCOPE_INTERNAL), "内网")
        self.assertEqual(mail_scope_label(MAIL_SCOPE_EXTERNAL), "外网")

    def test_contact_people_filters_invalid_values(self):
        contacts = contact_people(["alice@example.com", "", "invalid", "bob@example.com"])

        self.assertEqual(
            contacts,
            [
                {"name": "alice", "email": "alice@example.com"},
                {"name": "bob", "email": "bob@example.com"},
            ],
        )

    def test_merge_contact_lists_keeps_order_and_deduplicates_case_insensitive(self):
        merged = merge_contact_lists(
            ["alice@example.com", "bob@example.com"],
            ["ALICE@example.com", "carol@example.com"],
        )

        self.assertEqual(merged, ["alice@example.com", "bob@example.com", "carol@example.com"])

    @patch("release_tool.mail_contact_helpers.get_user_internal_email_settings")
    @patch("release_tool.mail_contact_helpers.get_internal_contact_settings")
    def test_contacts_for_internal_scope_merges_global_and_user_contacts(self, global_contacts, user_contacts):
        global_contacts.return_value = {
            "contacts_to": ["team@example.com"],
            "contacts_cc": ["lead@example.com"],
        }
        user_contacts.return_value = {
            "contacts_to": ["dev@example.com"],
            "contacts_cc": ["lead@example.com", "qa@example.com"],
            "contact_templates": [{"name": "default"}],
        }

        contacts = contacts_for_scope({"user_key": "u1"}, MAIL_SCOPE_INTERNAL)

        self.assertEqual(contacts["contacts_to"], ["team@example.com", "dev@example.com"])
        self.assertEqual(contacts["contacts_cc"], ["lead@example.com", "qa@example.com"])
        self.assertEqual(contacts["contact_templates"], [{"name": "default"}])

    @patch("release_tool.mail_contact_helpers.get_user_external_email_account_settings")
    def test_contacts_for_external_scope_uses_external_account_contacts(self, account_contacts):
        account_contacts.return_value = {
            "contacts_to": ["customer@example.com"],
            "contacts_cc": ["support@example.com"],
            "contact_templates": [],
        }

        contacts = contacts_for_scope({"user_key": "u1"}, MAIL_SCOPE_EXTERNAL)

        account_contacts.assert_called_once_with("u1")
        self.assertEqual(contacts["contacts_to"], ["customer@example.com"])
        self.assertEqual(contacts["contacts_cc"], ["support@example.com"])


if __name__ == "__main__":
    unittest.main()
