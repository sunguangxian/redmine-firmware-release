import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_tool.session_store import SQLiteSessionStore


class SQLiteSessionStoreTest(unittest.TestCase):
    def test_session_is_shared_between_store_instances_and_secrets_are_protected(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "release_tool.config_store.PROJECT_ROOT", Path(temp_dir)
        ):
            first = SQLiteSessionStore()
            second = SQLiteSessionStore()
            session = {
                "connected": True,
                "user_login": "alice",
                "password": "redmine-secret",
                "api_key": "api-secret",
            }

            first.set("sid-1", session)

            self.assertEqual(second.get("sid-1"), session)
            database = Path(temp_dir) / ".redmine-release-tool" / "release_tool.db"
            conn = sqlite3.connect(database)
            try:
                raw_payload = conn.execute("SELECT payload FROM server_sessions WHERE sid = 'sid-1'").fetchone()[0]
            finally:
                conn.close()
            self.assertNotIn("redmine-secret", raw_payload)
            self.assertNotIn("api-secret", raw_payload)


if __name__ == "__main__":
    unittest.main()
