import unittest
from unittest.mock import patch


class SessionConfigTest(unittest.TestCase):
    def test_bool_env_accepts_enabled_values(self):
        from release_tool.session_config import _bool_env

        with patch.dict("os.environ", {"X_TEST_BOOL": "true"}, clear=False):
            self.assertTrue(_bool_env("X_TEST_BOOL"))
        with patch.dict("os.environ", {"X_TEST_BOOL": "0"}, clear=False):
            self.assertFalse(_bool_env("X_TEST_BOOL"))

    def test_int_env_falls_back_on_invalid_value(self):
        from release_tool.session_config import _int_env

        with patch.dict("os.environ", {"X_TEST_INT": "bad"}, clear=False):
            self.assertEqual(_int_env("X_TEST_INT", 123), 123)
        with patch.dict("os.environ", {"X_TEST_INT": "60"}, clear=False):
            self.assertEqual(_int_env("X_TEST_INT", 123), 60)

    def test_samesite_env_allows_only_supported_values(self):
        from release_tool.session_config import _samesite_env

        with patch.dict("os.environ", {"X_TEST_SAMESITE": "Strict"}, clear=False):
            self.assertEqual(_samesite_env("X_TEST_SAMESITE"), "strict")
        with patch.dict("os.environ", {"X_TEST_SAMESITE": "invalid"}, clear=False):
            self.assertEqual(_samesite_env("X_TEST_SAMESITE"), "lax")


if __name__ == "__main__":
    unittest.main()
