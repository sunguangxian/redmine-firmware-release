import unittest
from unittest.mock import patch

from release_tool.external_account_contacts import external_account_key, get_external_account_contacts_for_user


class ExternalAccountContactsTest(unittest.TestCase):
    def test_account_key_is_scoped_to_local_user(self):
        self.assertNotEqual(
            external_account_key("redmine|alice", "shared@example.com"),
            external_account_key("redmine|bob", "shared@example.com"),
        )

    @patch("release_tool.external_account_contacts.get_user_external_email_settings")
    def test_user_cannot_query_contacts_for_another_smtp_account(self, settings):
        settings.return_value = {"smtp_user": "alice@example.com"}

        result = get_external_account_contacts_for_user("redmine|alice", "bob@example.com")

        self.assertEqual(result["contacts_to"], [])
        self.assertEqual(result["contact_templates"], [])


if __name__ == "__main__":
    unittest.main()
