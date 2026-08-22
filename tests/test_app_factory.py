import unittest

from release_tool.app_factory import app, create_app


class AppFactoryTest(unittest.TestCase):
    def test_create_app_is_idempotent(self):
        first = create_app()
        second = create_app()
        self.assertIsNot(first, second)
        self.assertEqual(
            {getattr(route, "path", "") for route in first.router.routes},
            {getattr(route, "path", "") for route in second.router.routes},
        )

    def test_key_api_routes_are_registered(self):
        paths = {getattr(route, "path", "") for route in app.router.routes}

        expected = {
            "/api/auth/login",
            "/api/auth/me",
            "/api/projects",
            "/api/releases",
            "/api/releases/detail",
            "/api/releases/publish",
            "/api/releases/plan",
            "/api/mail/settings",
            "/api/wiki-config/{project_id}",
            "/api/wiki-config/{project_id}/convert-preview",
            "/api/wiki-config/{project_id}/convert",
            "/api/legacy-migration/preview",
        }

        self.assertTrue(expected.issubset(paths), expected - paths)
        self.assertNotIn("/api/auth/clear-local-credentials", paths)


if __name__ == "__main__":
    unittest.main()
