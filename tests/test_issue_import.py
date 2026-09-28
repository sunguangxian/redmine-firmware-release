import io
import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from release_tool.dependencies import _current_client, _current_session
from release_tool.issue_import import commit_issue_sheet, preview_issue_sheet, project_import_options
from release_tool.issue_import_api import register_issue_import_routes
from release_tool.issue_sheet import parse_issue_workbook


def _workbook_bytes() -> bytes:
    book = Workbook()
    notes = book.active
    notes.title = "日报填写说明"
    notes.append(["日报填写说明", "这里没有问题列"])

    sheet = book.create_sheet("问题反馈")
    sheet.append(["EV760项目测试问题反馈"])
    sheet.append(["基本信息", "软件版本", "", "测试样品状态/来源"])
    sheet.append(["", "软件版本:V0.1.18 / MCU:V5.3.8.12 / EV760:V600R007C00B029", "", "EV760样机/正常"])
    sheet.append(["备注事项"])
    sheet.append(["", "序号", "发现日期", "测试项目或模块", "故障样品编号", "故障概述", "故障及风险详细说明", "故障等级"])
    sheet.append(["", 1, "9月23日", "应用软件", "", "全呼ID可以发起个呼呼叫。", "详细\n第二行", "3-High"])
    sheet.append(["", 2, "9月24日", "应用软件", "", "扫描列表管理，建议已添加进扫描列表的信道。", "建议说明", "2-Medium"])
    sheet.append(["", 2, "9月24日", "应用软件", "", "另一条序号重复。", "说明", "4-Very High"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class FakeRedmine:
    base_url = "http://redmine.local"

    def __init__(self):
        self.created = []

    def list_versions(self, project_id):
        self.project_id = project_id
        return [{"id": 2210, "name": "V5.3.8.12", "status": "open"}]

    def list_memberships(self, project_id):
        return [{"user": {"id": 18, "name": "小勇"}}]

    def list_users(self):
        return [{"id": 18, "login": "dongxiaoyong", "firstname": "小勇", "lastname": "董"}]

    def list_issue_priorities(self):
        return [
            {"id": 2, "name": "普通", "active": True},
            {"id": 3, "name": "高", "active": True},
            {"id": 4, "name": "紧急", "active": True},
        ]

    def get_project(self, project_id, include=""):
        return {"identifier": project_id, "trackers": [{"id": 1, "name": "错误"}, {"id": 2, "name": "功能"}]}

    def list_issues(self, project_id, *, limit_cap=5000):
        return [
            {
                "id": 2781,
                "subject": "全呼ID可以发起个呼呼叫。",
                "fixed_version": {"id": 2210, "name": "V5.3.8.12"},
            }
        ]

    def create_issue(self, project_id, fields):
        self.created.append(fields)
        return {"id": 3000 + len(self.created), "subject": fields["subject"]}


class IssueSheetParseTest(unittest.TestCase):
    def test_parses_problem_sheet_and_skips_instruction_sheet(self):
        parsed = parse_issue_workbook("KM2_V5.3.8.12新发现问题列表0924.xlsx", _workbook_bytes(), year=2026)

        self.assertEqual(parsed.used_sheets, ["问题反馈"])
        self.assertEqual(parsed.skipped_sheets, ["日报填写说明"])
        self.assertEqual(parsed.software_version, "V0.1.18")
        self.assertEqual(parsed.mcu, "V5.3.8.12")
        self.assertEqual(parsed.extra_versions, [("EV760", "V600R007C00B029")])
        self.assertEqual(parsed.sample, "EV760样机/正常")
        self.assertEqual(parsed.suggested_version, "V5.3.8.12")
        self.assertEqual([item.subject for item in parsed.issues], [
            "全呼ID可以发起个呼呼叫。",
            "扫描列表管理，建议已添加进扫描列表的信道。",
            "另一条序号重复。",
        ])
        self.assertEqual(parsed.issues[0].found_on, "2026-09-23")
        self.assertEqual(parsed.issues[0].priority_name, "高")
        self.assertEqual(parsed.issues[0].tracker_name, "错误")
        self.assertIn("详细\n第二行", parsed.issues[0].description)
        self.assertEqual(parsed.issues[1].priority_name, "普通")
        self.assertEqual(parsed.issues[1].tracker_name, "功能")
        self.assertEqual(parsed.issues[2].seq_note, "（表中序号重复）")
        self.assertEqual(parsed.issues[2].priority_name, "紧急")
        self.assertTrue(any("序号重复" in item for item in parsed.warnings))


class IssueImportServiceTest(unittest.TestCase):
    def test_preview_marks_existing_subject_and_suggests_version(self):
        preview = preview_issue_sheet(
            FakeRedmine(),
            filename="KM2_V5.3.8.12问题.xlsx",
            content=_workbook_bytes(),
            project_id="km2",
            year=2026,
        )

        self.assertEqual(preview["counts"], {"total": 3, "new": 2, "duplicate": 1})
        self.assertEqual(preview["suggested_version"]["id"], 2210)
        self.assertTrue(preview["issues"][0]["duplicate"])
        self.assertEqual(preview["issues"][0]["existing_id"], 2781)
        self.assertEqual(preview["issues"][1]["tracker_name"], "功能")

    def test_assignee_label_uses_chinese_name_order(self):
        options = project_import_options(FakeRedmine(), "km2")
        self.assertEqual(options["assignees"], [{"id": 18, "name": "董小勇（dongxiaoyong）", "login": "dongxiaoyong"}])

    def test_commit_creates_only_selected_new_rows(self):
        client = FakeRedmine()
        preview = preview_issue_sheet(
            client,
            filename="issues.xlsx",
            content=_workbook_bytes(),
            project_id="km2",
            year=2026,
        )
        keys = [row["row_key"] for row in preview["issues"]]
        result = commit_issue_sheet(
            client,
            filename="issues.xlsx",
            content=_workbook_bytes(),
            project_id="km2",
            assigned_to_id=18,
            version_id=2210,
            row_keys=keys,
            year=2026,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["created"]), 2)
        self.assertEqual(result["skipped"][0]["reason"], "已存在 #2781")
        self.assertEqual(client.created[0]["assigned_to_id"], 18)
        self.assertEqual(client.created[0]["fixed_version_id"], 2210)
        self.assertEqual(client.created[0]["tracker_id"], 2)
        self.assertEqual(client.created[0]["priority_id"], 2)
        self.assertEqual(client.created[1]["priority_id"], 4)
        self.assertEqual(client.created[1]["start_date"], "2026-09-24")

    def test_commit_requires_assignee(self):
        with self.assertRaisesRegex(Exception, "指派人"):
            commit_issue_sheet(
                FakeRedmine(),
                filename="issues.xlsx",
                content=_workbook_bytes(),
                project_id="km2",
                assigned_to_id=0,
                version_id=2210,
                row_keys=["问题反馈\t7"],
                year=2026,
            )


class IssueImportApiTest(unittest.TestCase):
    def _http(self, session, client):
        app = FastAPI()
        register_issue_import_routes(app)
        app.dependency_overrides[_current_session] = lambda: session
        app.dependency_overrides[_current_client] = lambda: client
        return TestClient(app)

    def test_non_admin_is_rejected(self):
        session = {"connected": True, "is_admin": False, "user_login": "tester", "projects": []}
        with self._http(session, FakeRedmine()) as http:
            response = http.get("/api/issue-import/options", params={"project_id": "km2"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("管理员", response.json()["detail"])

    def test_preview_and_commit_round_trip(self):
        session = {"connected": True, "is_admin": True, "user_login": "admin", "projects": [{"identifier": "km2"}]}
        client = FakeRedmine()
        content = _workbook_bytes()
        with self._http(session, client) as http, patch("release_tool.issue_import_api.record_audit") as audit:
            preview = http.post(
                "/api/issue-import/preview",
                data={"project_id": "km2", "year": "2026"},
                files={"file": ("KM2_V5.3.8.12问题.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            body = preview.json()
            keys = [row["row_key"] for row in body["issues"] if not row["duplicate"]]
            commit = http.post(
                "/api/issue-import/commit",
                data={
                    "project_id": "km2",
                    "assigned_to_id": "18",
                    "version_id": "2210",
                    "year": "2026",
                    "row_keys_json": json.dumps(keys),
                },
                files={"file": ("KM2_V5.3.8.12问题.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertEqual(len(commit.json()["created"]), 2)
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["action"], "issue_import")


if __name__ == "__main__":
    unittest.main()
