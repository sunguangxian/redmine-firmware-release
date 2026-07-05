import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from release_tool.dependencies import (
    SESSION_COOKIE,
    SESSION_STORE,
    SESSIONS,
    _current_client,
    _current_session,
    _json_error,
    _public_session,
    _require_admin,
    _user_key,
)


class DependenciesTest(unittest.TestCase):
    def tearDown(self):
        SESSIONS.clear()

    def test_user_key_normalizes_base_url(self):
        self.assertEqual(_user_key("http://redmine.local/", "admin"), "http://redmine.local|admin")

    def test_json_error_uses_detail_and_status_code(self):
        error = _json_error("错误", 403)
        self.assertIsInstance(error, HTTPException)
        self.assertEqual(error.status_code, 403)
        self.assertEqual(error.detail, "错误")

    def test_current_session_rejects_missing_cookie(self):
        request = Mock()
        request.cookies = {}

        with self.assertRaises(HTTPException) as ctx:
            _current_session(request)

        self.assertEqual(ctx.exception.status_code, 401)

    def test_current_session_returns_stored_session(self):
        session = {"connected": True, "user_login": "admin"}
        SESSION_STORE.set("sid", session)
        request = Mock()
        request.cookies = {SESSION_COOKIE: "sid"}

        self.assertIs(_current_session(request), session)

    def test_require_admin_rejects_normal_user(self):
        with self.assertRaises(HTTPException) as ctx:
            _require_admin({"is_admin": False})

        self.assertEqual(ctx.exception.status_code, 403)

    def test_public_session_hides_credentials(self):
        public = _public_session(
            {
                "connected": True,
                "user_login": "admin",
                "is_admin": True,
                "projects": [{"identifier": "demo"}],
                "password": "secret",
            }
        )

        self.assertEqual(public.user_login, "admin")
        self.assertTrue(public.is_admin)
        self.assertEqual(public.projects, [{"identifier": "demo"}])
        self.assertFalse(hasattr(public, "password"))

    def test_current_client_uses_session_auth_fields(self):
        client = _current_client(
            {
                "base_url": "http://redmine.local",
                "username": "admin",
                "password": "secret",
                "api_key": "key",
                "auth_mode": "api_key",
            }
        )

        self.assertEqual(client.base_url, "http://redmine.local")
        self.assertEqual(client.auth_mode, "api_key")
        self.assertEqual(client.session.headers.get("X-Redmine-API-Key"), "key")


if __name__ == "__main__":
    unittest.main()
