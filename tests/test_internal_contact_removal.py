import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from release_tool.config_store import (
    _init_db,
    get_internal_contact_settings,
    get_user_internal_email_settings,
    store_internal_contact_settings,
    store_user_internal_email_settings,
)
from release_tool.external_account_contacts import (
    get_external_account_contact_settings,
    store_user_external_email_account_settings,
)
from release_tool.internal_contact_people import get_internal_contact_people, store_internal_contact_people
from release_tool.mail_settings_api import register_mail_settings_routes
from release_tool.schemas import AdminMailSettingsRequest, ContactConfig, ContactPersonConfig, SmtpServerConfig


@contextmanager
def temp_database(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


class InternalContactRemovalTest(unittest.TestCase):
    def test_admin_save_removes_departed_contact_from_every_address_book(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "release_tool.db"

            @contextmanager
            def fake_db():
                with temp_database(database) as conn:
                    yield conn

            patches = [
                patch("release_tool.config_store.db", fake_db),
                patch("release_tool.internal_contact_people.db", fake_db),
                patch("release_tool.external_account_contacts.db", fake_db),
                patch("release_tool.audit_log.db", fake_db),
            ]
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in patches])

            store_internal_contact_people(
                [
                    {"name": "在职", "email": "stay@example.com"},
                    {"name": "离职", "email": "left@example.com"},
                ]
            )
            store_internal_contact_settings(
                contacts_to=["stay@example.com", "left@example.com"],
                contacts_cc=["left@example.com"],
            )
            store_user_internal_email_settings(
                "former-user",
                smtp_user="former",
                smtp_password="secret",
                smtp_from="former@example.com",
                contacts_to=["left@example.com", "stay@example.com"],
                contacts_cc=["left@example.com"],
                contact_templates=[
                    {
                        "name": "默认",
                        "contacts_to": [{"name": "离职", "email": "left@example.com"}],
                        "contacts_cc": [{"name": "在职", "email": "stay@example.com"}],
                    }
                ],
            )
            store_user_external_email_account_settings(
                "former-user",
                smtp_user="former@example.com",
                smtp_password="secret",
                smtp_from="former@example.com",
                contacts_to=["left@example.com", "customer@example.com"],
                contacts_cc=[],
                contacts_to_people=[
                    {"name": "离职", "email": "left@example.com"},
                    {"name": "客户", "email": "customer@example.com"},
                ],
                contact_templates=[
                    {
                        "name": "客户组",
                        "contacts_to": [
                            {"name": "离职", "email": "left@example.com"},
                            {"name": "客户", "email": "customer@example.com"},
                        ],
                        "contacts_cc": [],
                    }
                ],
            )

            app = FastAPI()
            register_mail_settings_routes(app)
            endpoint = next(
                route.endpoint
                for route in app.router.routes
                if getattr(route, "path", "") == "/api/mail/admin-settings"
            )
            result = endpoint(
                AdminMailSettingsRequest(
                    internal_server=SmtpServerConfig(smtp_host="mail.local", smtp_port=25),
                    external_server=SmtpServerConfig(smtp_host="smtp.example.com", smtp_port=465, use_tls=True),
                    internal_contacts=ContactConfig(
                        contacts=["stay@example.com"],
                        contacts_to=["stay@example.com"],
                        contacts_cc=[],
                        contacts_people=[ContactPersonConfig(name="在职", email="stay@example.com")],
                    ),
                ),
                session={"is_admin": True, "user_login": "admin"},
            )

            self.assertTrue(result["ok"])
            self.assertEqual(get_internal_contact_settings()["contacts_to"], ["stay@example.com"])
            self.assertEqual(get_internal_contact_settings()["contacts_cc"], [])
            self.assertEqual([item["email"] for item in get_internal_contact_people()], ["stay@example.com"])
            personal = get_user_internal_email_settings("former-user")
            self.assertEqual(personal["contacts_to"], ["stay@example.com"])
            self.assertEqual(personal["contacts_cc"], [])
            self.assertEqual(personal["contact_templates"][0]["contacts_cc"][0]["email"], "stay@example.com")
            self.assertEqual(personal["contact_templates"][0]["contacts_to"], [])
            external = get_external_account_contact_settings("former-user", "former@example.com")
            self.assertEqual(external["contacts_to"], ["customer@example.com"])
            self.assertEqual(external["contact_templates"][0]["contacts_to"][0]["email"], "customer@example.com")


if __name__ == "__main__":
    unittest.main()
