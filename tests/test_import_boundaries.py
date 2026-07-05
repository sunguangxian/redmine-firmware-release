import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "release_tool"

ALLOWED_API_APP_IMPORTERS = {
    "app_factory.py",
}

FORBIDDEN_API_APP_NAMES = {
    "_current_session",
    "_current_client",
    "_require_admin",
    "_json_error",
    "_send_release_notice",
    "_validate_notice_preflight",
    "_build_email_settings",
    "_mail_scope_label",
    "_contacts_for_scope",
    "_list_release_rows",
    "_validate_release_preflight",
    "_append_legacy_job_log",
    "_legacy_job_snapshot",
    "_set_legacy_job_state",
}


class ImportBoundariesTest(unittest.TestCase):
    def test_api_modules_do_not_import_business_helpers_from_api_app(self):
        violations: list[str] = []
        for path in sorted(API_DIR.glob("*_api.py")):
            if path.name in ALLOWED_API_APP_IMPORTERS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module != "api_app" and node.module != "release_tool.api_app" and node.module != ".api_app":
                    continue
                imported = {alias.name for alias in node.names}
                forbidden = imported & FORBIDDEN_API_APP_NAMES
                if forbidden:
                    violations.append(f"{path.name}: {', '.join(sorted(forbidden))}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
