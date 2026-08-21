import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException, Response

from release_tool.auth_api import _set_session_cookie, register_auth_routes
from release_tool.dependencies import SESSION_COOKIE, SESSIONS
from release_tool.redmine_api import RedmineError
from release_tool.schemas import LoginRequest


class FakeRedmineClient:
    def __init__(self, *args, **kwargs):
        pass

    def test_login(self):
        return {"user": {"login": "alice", "admin": True}}

    def list_projects(self):
        return []


class FailingRedmineClient(FakeRedmineClient):
    def test_login(self):
        raise RedmineError("用户名或密码错误")


class AuthCookieTest(unittest.TestCase):
    def tearDown(self):
        SESSIONS.clear()

    def _endpoint(self, app, path, method):
        for route in app.router.routes:
            if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
                return route.endpoint
        self.fail(f"Route not found: {method} {path}")

    def _session_cookie_value(self, response):
        prefix = f"{SESSION_COOKIE}="
        values = []
        for name, value in response.raw_headers:
            if name.lower() != b"set-cookie":
                continue
            cookie = value.decode("latin-1")
            if cookie.startswith(prefix):
                values.append(cookie.split(";", 1)[0].split("=", 1)[1].strip('"'))
        return next(value for value in reversed(values) if value)

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
            login = self._endpoint(app, "/api/auth/login", "POST")
            me = self._endpoint(app, "/api/auth/me", "GET")

            login_response = Response()
            login(
                LoginRequest(username="alice", password="secret", remember=True),
                Mock(cookies={}),
                login_response,
            )

            first_sid = self._session_cookie_value(login_response)
            self.assertTrue(first_sid)
            self.assertTrue(me(Mock(cookies={SESSION_COOKIE: first_sid}), Response()).connected)
            with self.assertRaises(HTTPException) as exc:
                me(Mock(cookies={}), Response())
            self.assertEqual(exc.exception.status_code, 401)
            legacy_saved_login_reader.assert_not_called()
            legacy_saved_login_writer.assert_not_called()

    def test_form_login_sets_cookie_and_redirects_to_frontend(self):
        app = FastAPI()
        register_auth_routes(app)
        login_form = self._endpoint(app, "/api/auth/login-form", "POST")

        with patch("release_tool.auth_api.RedmineClient", FakeRedmineClient):
            response = login_form(
                request=Mock(cookies={}),
                username="alice",
                password="secret",
                remember=True,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertTrue(self._session_cookie_value(response))

    def test_form_login_failure_redirects_with_error_and_without_session(self):
        app = FastAPI()
        register_auth_routes(app)
        login_form = self._endpoint(app, "/api/auth/login-form", "POST")

        with patch("release_tool.auth_api.RedmineClient", FailingRedmineClient):
            response = login_form(
                request=Mock(cookies={}),
                username="alice",
                password="bad",
                remember=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("login_error=", response.headers["location"])
        self.assertEqual(SESSIONS, {})


if __name__ == "__main__":
    unittest.main()
