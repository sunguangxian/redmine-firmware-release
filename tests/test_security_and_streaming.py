import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from release_tool.attachment_policy import content_size, sha256_hex, validate_attachment_batch
from release_tool.auth_api import _check_login_rate_limit, _clear_login_failures, _record_login_failure
from release_tool.app_factory import main


class SecurityAndStreamingTest(unittest.TestCase):
    def test_non_loopback_server_refuses_plain_http_by_default(self):
        with patch.dict(
            "os.environ",
            {"RELEASE_TOOL_HOST": "0.0.0.0", "RELEASE_TOOL_PORT": "7860"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "明文 HTTP"):
                main()

    def test_file_like_attachment_is_hashed_without_changing_position(self):
        content = io.BytesIO(b"firmware-content")
        content.seek(3)

        digest = sha256_hex(content)

        self.assertEqual(content.tell(), 3)
        self.assertEqual(content_size(content), len(b"firmware-content"))
        self.assertEqual(len(digest), 64)
        validate_attachment_batch([("firmware.bin", "", content)])

    def test_login_failures_are_rate_limited_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "release_tool.config_store.PROJECT_ROOT", Path(temp_dir)
        ), patch.dict(
            "os.environ",
            {"RELEASE_TOOL_LOGIN_RATE_LIMIT": "2", "RELEASE_TOOL_LOGIN_RATE_WINDOW_SECONDS": "60"},
        ):
            _record_login_failure("client-1")
            _record_login_failure("client-1")
            with self.assertRaises(HTTPException) as context:
                _check_login_rate_limit("client-1")
            self.assertEqual(context.exception.status_code, 429)

            _clear_login_failures("client-1")
            _check_login_rate_limit("client-1")


if __name__ == "__main__":
    unittest.main()
