import unittest

from fastapi import HTTPException

from release_tool.access_control import clamp_history_limit, list_visible_history, require_project_access, visible_project_ids


class AccessControlTest(unittest.TestCase):
    def test_visible_project_ids_ignores_empty_identifier(self):
        session = {
            "projects": [
                {"identifier": "dp580"},
                {"identifier": ""},
                {"name": "missing identifier"},
                {"identifier": "rk3308"},
            ]
        }
        self.assertEqual(visible_project_ids(session), {"dp580", "rk3308"})

    def test_require_project_access_allows_admin(self):
        require_project_access({"is_admin": True, "projects": []}, "any-project")

    def test_require_project_access_allows_visible_project(self):
        session = {"is_admin": False, "projects": [{"identifier": "dp580"}]}

        require_project_access(session, "dp580")

    def test_require_project_access_rejects_invisible_project(self):
        session = {"is_admin": False, "projects": [{"identifier": "dp580"}]}
        with self.assertRaises(HTTPException) as cm:
            require_project_access(session, "dp990")
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(cm.exception.detail, "无权访问该项目")

    def test_require_project_access_rejects_blank_project_for_normal_user(self):
        session = {"is_admin": False, "projects": [{"identifier": "dp580"}]}

        with self.assertRaises(HTTPException) as cm:
            require_project_access(session, "")

        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(cm.exception.detail, "普通用户必须指定项目")

    def test_clamp_history_limit_bounds_values(self):
        self.assertEqual(clamp_history_limit(0), 50)
        self.assertEqual(clamp_history_limit(-1), 1)
        self.assertEqual(clamp_history_limit(500), 200)
        self.assertEqual(clamp_history_limit("bad"), 50)

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

    def test_list_visible_history_rejects_invisible_project(self):
        session = {"is_admin": False, "projects": [{"identifier": "dp580"}]}

        with self.assertRaises(HTTPException) as cm:
            list_visible_history(
                session,
                project_id="dp990",
                loader=lambda *, project_id, wiki_title, limit: [],
            )

        self.assertEqual(cm.exception.status_code, 403)

    def test_list_visible_history_admin_without_project_can_query_all(self):
        session = {"is_admin": True, "projects": []}
        calls = []

        def loader(*, project_id, wiki_title, limit):
            calls.append((project_id, wiki_title, limit))
            return [{"id": 1, "project_id": project_id}]

        items = list_visible_history(session, wiki_title="Release_A", limit=500, loader=loader)

        self.assertEqual(items, [{"id": 1, "project_id": ""}])
        self.assertEqual(calls, [("", "Release_A", 200)])


if __name__ == "__main__":
    unittest.main()
