import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from release_tool import audit_log, legacy_job_store, mail_history
from release_tool.api_app import _send_release_notice
from release_tool.config_store import _init_db, clear_local_credentials, get_saved_login, store_login
from release_tool.email_sender import EmailSendError, EmailSettings


@contextmanager
def temp_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


class PersistentJobsAndMailHistoryTest(unittest.TestCase):
    def test_legacy_job_snapshot_is_read_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = f"{tmpdir}/jobs.db"
            with patch("release_tool.legacy_job_store.db", lambda: temp_db(db_file)):
                legacy_job_store.create_legacy_job(
                    "job-1",
                    project_id="dp5x",
                    entry_pages=["Changelog"],
                    release_detail_mode="inline",
                )
                legacy_job_store.append_legacy_job_log("job-1", "开始")
                legacy_job_store.update_legacy_job("job-1", status="succeeded", result={"ok": True})
                snapshot = legacy_job_store.legacy_job_snapshot("job-1")

            self.assertEqual(snapshot["job_id"], "job-1")
            self.assertEqual(snapshot["status"], "succeeded")
            self.assertTrue(snapshot["logs"])
            self.assertEqual(snapshot["result"], {"ok": True})

    def test_notice_failure_records_mail_history_without_patch_wrapper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = f"{tmpdir}/mail.db"

            class Client:
                base_url = "http://redmine.example"

            def fail_send(*args, **kwargs):
                raise EmailSendError("SMTP failed")

            with patch("release_tool.mail_history.db", lambda: temp_db(db_file)), patch(
                "release_tool.api_app._build_email_settings",
                return_value=(EmailSettings("smtp", 25, "user", "pw", "from@example.com", False), [], []),
            ), patch("release_tool.api_app.send_release_email", fail_send):
                with self.assertRaises(EmailSendError):
                    _send_release_notice(
                        session={"user_login": "tester"},
                        client=Client(),
                        project_id="dp5x",
                        wiki_title="Release_Notes",
                        version_name="V1.0.0",
                        file_rows=[],
                        mail_scope="internal",
                        mail_to=["to@example.com"],
                        mail_cc=[],
                        mail_subject="subject",
                        mail_body="body",
                        send_type="publish",
                    )
                rows = mail_history.list_mail_history(project_id="dp5x", wiki_title="Release_Notes", version_name="V1.0.0")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "failed")
            self.assertEqual(rows[0]["send_type"], "publish")
            self.assertIn("SMTP failed", rows[0]["error_message"])

    def test_saved_redmine_secret_is_protected_and_clearable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = f"{tmpdir}/settings.db"

            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            with patch("release_tool.config_store.db", lambda: temp_db(db_file)), patch(
                "release_tool.config_store.config_dir",
                lambda: config_dir,
            ), patch.dict("os.environ", {"RELEASE_TOOL_SAVE_LOGIN_SECRETS": "1"}, clear=False):
                store_login(
                    "http://redmine.example",
                    "alice",
                    "secret-password",
                    True,
                    auth_mode="password",
                )
                conn = sqlite3.connect(db_file)
                try:
                    raw_password = conn.execute("SELECT value FROM app_settings WHERE key = 'password'").fetchone()[0]
                finally:
                    conn.close()
                self.assertNotEqual(raw_password, "secret-password")
                self.assertEqual(get_saved_login()["password"], "secret-password")
                clear_local_credentials()
                self.assertFalse(get_saved_login()["remember"])
                self.assertEqual(get_saved_login()["password"], "")

    def test_audit_log_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = f"{tmpdir}/audit.db"
            with patch("release_tool.audit_log.db", lambda: temp_db(db_file)):
                audit_log.record_audit(
                    actor="admin",
                    action="wiki_config_updated",
                    target_type="wiki_config",
                    target_id="dp5x",
                    details={"release_detail_mode": "page"},
                )
                rows = audit_log.list_audit_logs()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["actor"], "admin")
            self.assertEqual(rows[0]["target_id"], "dp5x")
            self.assertEqual(rows[0]["details"]["release_detail_mode"], "page")


if __name__ == "__main__":
    unittest.main()
