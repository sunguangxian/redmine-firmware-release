import unittest

from fastapi import HTTPException

from release_tool.access_control import list_visible_history, require_project_access, visible_project_ids


class AccessControlTest(unittest.TestCase):
    def test_visible_project_ids_ignores_empty_identifier(self):
        session = {
            "projects": [
                {"identifier": "dp580"},
                {"identifier": ""},
                {"name": "missing identifier"},
            ]
        }
        self.assertEqual(visible_project_ids(session), {"dp580"})

    def test_require_project_access_allows_admin(self):
        require_project_access({"is_admin": True, "projects": []}, "any-project")

    def test_require_project_access_rejects_invisible_project(self):
        session = {"is_admin": False, "projects": [{"identifier": "dp580"}]}
        with self.assertRaises(HTTPException) as cm:
            require_project_access(session, "dp990")
        self.assertEqual(cm.exception.status_code, 403)

    def test_list_visible_history_limits_normal_user_to_visible_projects(self):
        session = {
            "is_admin": False,
            "projects": [{"identifier": "dp580"}, {"identifier": "dp990"}],
        }

        def loader(*, project_id, wiki_title, limit):
            return [
                {"id": 1, "project_id": project_id, "wiki_title": wiki_title},
                {"id": 3, "project_id": project_id, "wiki_title": wiki_title},
            ][:limit]

        items = list_visible_history(session, wiki_title="Release_A", limit=3, loader=loader)
        self.assertEqual([item["id"] for item in items], [3, 3, 1])
        self.assertEqual({item["project_id"] for item in items}, {"dp580", "dp990"})


if __name__ == "__main__":
    unittest.main()
