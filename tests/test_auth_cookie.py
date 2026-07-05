import unittest

from fastapi import Response

from release_tool.auth_api import _set_session_cookie
from release_tool.dependencies import SESSION_COOKIE


class AuthCookieTest(unittest.TestCase):
    def test_session_cookie_has_http_only_and_max_age(self):
        response = Response()
        _set_session_cookie(response, "sid-test")
        cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"{SESSION_COOKIE}=sid-test", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Max-Age=", cookie)
        self.assertIn("SameSite=", cookie)


if __name__ == "__main__":
    unittest.main()
