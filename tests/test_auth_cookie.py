import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from release_tool.auth_api import _set_session_cookie, register_auth_routes
from release_tool.dependencies import SESSION_COOKIE, SESSIONS


class FakeRedmineClient:
    def __init__(self, *args, **kwargs):
        pass

    def test_login(self):
        return {"user": {"login": "alice", "admin": True}}

    def list_projects(self):
        return []


class AuthCookieTest(unittest.TestCase):
    def tearDown(self):
        SESSIONS.clear()

    def test_session_cookie_is_browser_session_cookie_by_default(self):
        response = Response()
        _set_session_cookie(response, "sid-test")
        cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"{SESSION_COOKIE}=sid-test", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertNotIn("Max-Age=", cookie)
        self.assertIn("SameSite=", cookie)

    def test_remembered_session_cookie_has_max_age(self):
        response = Response()
        _set_session_cookie(response, "sid-test", remember=True)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("Max-Age=", cookie)

    def test_remembered_login_is_not_shared_with_another_client(self):
        app = FastAPI()
        register_auth_routes(app)
        saved_login = {
            "auth_mode": "password",
            "username": "alice",
            "password": "secret",
            "api_key": "",
            "remember": True,
        }
        legacy_saved_login_reader = Mock(return_value=saved_login)
        legacy_saved_login_writer = Mock()

        with patch("release_tool.auth_api.RedmineClient", FakeRedmineClient), patch(
            "release_tool.auth_api.get_saved_login", legacy_saved_login_reader, create=True
        ), patch("release_tool.auth_api.store_login", legacy_saved_login_writer, create=True):
            first_client = TestClient(app)
            second_client = TestClient(app)

            login_response = first_client.post(
                "/api/auth/login",
                json={"username": "alice", "password": "secret", "remember": True},
            )
            self.assertEqual(login_response.status_code, 200)
            self.assertEqual(first_client.get("/api/auth/me").status_code, 200)
            self.assertEqual(second_client.get("/api/auth/me").status_code, 401)
            legacy_saved_login_reader.assert_not_called()
            legacy_saved_login_writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
