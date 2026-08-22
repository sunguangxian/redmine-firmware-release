import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

from release_tool.mail_settings_api import register_mail_settings_routes


class MailSettingsApiTest(unittest.TestCase):
    def _endpoint(self, app, path, method):
        return next(
            route.endpoint
            for route in app.router.routes
            if getattr(route, "path", "") == path and method in route.methods
        )

    def test_settings_hides_saved_mail_passwords_until_reauthenticated(self):
        app = FastAPI()
        register_mail_settings_routes(app)
        endpoint = self._endpoint(app, "/api/mail/settings", "GET")
        internal = {
            "smtp_user": "inside",
            "smtp_password": "inside-secret",
            "smtp_from": "inside@example.com",
            "contacts_to": [],
            "contacts_cc": [],
            "contact_templates": [],
        }
        external = {
            "smtp_user": "outside",
            "smtp_password": "outside-secret",
            "smtp_from": "outside@example.com",
            "contacts_to": [],
            "contacts_cc": [],
            "contact_templates": [],
        }
        server = {"smtp_host": "smtp.example.com", "smtp_port": 25, "smtp_from": "", "use_tls": False}

        with patch("release_tool.mail_settings_api.get_email_server_settings", return_value=server), patch(
            "release_tool.mail_settings_api.get_internal_contact_settings",
            return_value={"contacts_to": [], "contacts_cc": [], "contact_templates": []},
        ), patch("release_tool.mail_settings_api.get_internal_contact_people", return_value=[]), patch(
            "release_tool.mail_settings_api.get_user_internal_email_settings", return_value=internal
        ), patch("release_tool.mail_settings_api.get_user_external_email_account_settings", return_value=external):
            result = endpoint(session={"user_key": "alice", "is_admin": False})

        self.assertEqual(result["user_internal"]["smtp_password"], "")
        self.assertEqual(result["user_external"]["smtp_password"], "")
        self.assertTrue(result["user_internal"]["smtp_password_set"])
        self.assertTrue(result["user_external"]["smtp_password_set"])

    def test_reveal_passwords_validates_redmine_credential(self):
        from release_tool.schemas import MailPasswordRevealRequest

        app = FastAPI()
        register_mail_settings_routes(app)
        endpoint = self._endpoint(app, "/api/mail/passwords/reveal", "POST")
        session = {
            "user_key": "alice",
            "base_url": "https://redmine.example.com",
            "username": "alice",
            "auth_mode": "password",
            "password": "redmine-secret",
        }
        with patch("release_tool.mail_settings_api.RedmineClient") as client, patch(
            "release_tool.mail_settings_api.get_user_internal_email_settings",
            return_value={"smtp_password": "inside-secret"},
        ), patch(
            "release_tool.mail_settings_api.get_user_external_email_account_settings",
            return_value={"smtp_password": "outside-secret"},
        ):
            result = endpoint(
                MailPasswordRevealRequest(credential="redmine-secret"),
                request=SimpleNamespace(state=SimpleNamespace(session_sid="")),
                session=session,
            )

        client.return_value.test_login.assert_called_once_with()
        self.assertEqual(result["internal_password"], "inside-secret")
        self.assertEqual(result["external_password"], "outside-secret")


if __name__ == "__main__":
    unittest.main()
