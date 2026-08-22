import unittest

from fastapi.testclient import TestClient

from release_tool.app_factory import create_app


class ApiIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(create_app())
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def test_public_health_does_not_expose_local_paths_or_redmine_url(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertNotIn("database", payload)
        self.assertNotIn("redmine_base_url", payload)

    def test_detailed_database_health_requires_login(self):
        response = self.client.get("/api/health/db")

        self.assertEqual(response.status_code, 401)

    def test_removed_clear_credentials_endpoint_is_not_available(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertNotIn("/api/auth/clear-local-credentials", paths)


if __name__ == "__main__":
    unittest.main()
