"""Gradio UI 入口。"""

from __future__ import annotations

import traceback
from datetime import date
from pathlib import Path

import gradio as gr

from .config_store import get_last_project, get_saved_login, set_last_project, store_login
from .index_sync import IndexSync
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import (
    PRODUCT_LINES,
    ReleaseForm,
    format_release_files,
    parse_release_page,
    proj_tag_from_project,
)

# 全局会话（单用户桌面工具）
_session: dict = {"client": None, "projects": []}


def _client() -> RedmineClient | None:
    return _session.get("client")


def _connect(base_url: str, username: str, password: str, remember: bool) -> tuple[str, gr.Dropdown, gr.Dropdown]:
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url or not username or not password:
        return "请填写 Redmine 地址、用户名和密码", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])

    try:
        client = RedmineClient(base_url, username, password)
        account = client.test_login()
        _session["client"] = client
        projects = client.list_projects()
        _session["projects"] = projects
        store_login(base_url, username, password, remember)

        choices = [(f"{p['name']} ({p['identifier']})", p["identifier"]) for p in projects]
        last = get_last_project()
        default = last if last in [c[1] for c in choices] else (choices[0][1] if choices else None)
        user_label = account.get("user", {}).get("login", username)
        msg = f"已连接：{user_label}，服务器：{base_url}，共 {len(projects)} 个项目"
        return msg, gr.Dropdown(choices=choices, value=default), gr.Dropdown(choices=choices, value=default)
    except RedmineError as exc:
        _session["client"] = None
        return f"连接失败：{exc}", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    except Exception as exc:
        _session["client"] = None
        return f"连接失败：{exc}", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])


def _load_saved() -> tuple[str, str, str, bool]:
    saved = get_saved_login()
    return saved["base_url"], saved["username"], saved["password"], saved["remember"]


def _list_releases(project_id: str) -> str:
    client = _client()
    if not client:
        return "请先连接 Redmine"
    if not project_id:
        return "请选择项目"
    set_last_project(project_id)
    try:
        pub = ReleasePublisher(client)
        releases = pub.list_releases(project_id)
        if not releases:
            return "（暂无 Release 页）"
        lines = ["| 版本 | 日期 | 产品线 | Wiki 页 | 摘要 |", "|---|---|---|---|---|"]
        for item in releases:
            lines.append(
                f"| {item['version']} | {item['date']} | {item['product_line']} "
                f"| {item['title']} | {item['summary'][:40]} |"
            )
        return "\n".join(lines)
    except RedmineError as exc:
        return f"加载失败：{exc}"


def _load_release_to_form(project_id: str, wiki_title: str) -> tuple:
    client = _client()
    default_line = list(PRODUCT_LINES.keys())[0]
    if not client or not project_id or not wiki_title:
        return "", "", "", default_line, "", "（未选择已有版本）", False
    page = client.get_wiki_page(project_id, wiki_title)
    if not page:
        return "", "", "", default_line, "", "（未找到版本页面）", False
    parsed = parse_release_page(wiki_title, page.get("text", ""))
    return (
        parsed["version_name"],
        parsed["release_date"],
        parsed["commit"],
        parsed["product_line"],
        parsed["changelog"],
        format_release_files(parsed.get("files", [])),
        False,
    )


def _release_choices(project_id: str) -> gr.Dropdown:
    client = _client()
    if not client or not project_id:
        return gr.Dropdown(choices=[])
    try:
        pub = ReleasePublisher(client)
        releases = pub.list_releases(project_id)
        choices = [(f"{r['version']} — {r['title']}", r["title"]) for r in releases]
        return gr.Dropdown(choices=choices)
    except RedmineError:
        return gr.Dropdown(choices=[])


def _publish(
    project_id: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog: str,
    files: list,
    replace_attachments: bool,
    edit_title: str,
) -> tuple[str, str]:
    client = _client()
    if not client:
        return "请先连接 Redmine", _list_releases(project_id)
    if not project_id:
        return "请选择项目", ""
    if not version_name or not release_date or not commit:
        return "请填写版本号、日期和 Commit", _list_releases(project_id)

    items = [line.strip() for line in (changelog or "").splitlines() if line.strip()]
    if not items:
        return "请填写至少一条变更说明（每行一条）", _list_releases(project_id)

    file_rows: list[tuple[str, str, bytes]] = []
    for f in files or []:
        path = f if isinstance(f, str) else f.name
        p = Path(path)
        if p.exists():
            file_rows.append((p.name, "", p.read_bytes()))

    form = ReleaseForm(
        project_id=project_id,
        proj_tag=proj_tag_from_project(project_id, edit_title or None),
        version_name=version_name.strip(),
        release_date=release_date.strip(),
        commit=commit.strip(),
        product_line=product_line,
        changelog_items=items,
        files=file_rows,
        wiki_title=edit_title or None,
        replace_attachments=bool(replace_attachments),
    )

    try:
        pub = ReleasePublisher(client)
        title = pub.publish(form)
        if edit_title and replace_attachments:
            note = "发布成功（已替换 Wiki 中的附件列表，旧项目文件未删除）"
        elif edit_title and file_rows:
            note = "发布成功（已保留旧附件并追加新附件）"
        elif edit_title:
            note = "发布成功（已保留旧附件）"
        else:
            note = "发布成功"
        return f"{note}：{title}", _list_releases(project_id)
    except RedmineError as exc:
        return f"发布失败：{exc}", _list_releases(project_id)
    except Exception as exc:
        return f"发布失败：{exc}\n{traceback.format_exc()}", _list_releases(project_id)


def _refresh_index(project_id: str) -> tuple[str, str]:
    client = _client()
    if not client:
        return "请先连接 Redmine", ""
    if not project_id:
        return "请选择项目", ""
    try:
        count = IndexSync(client, project_id).refresh_all()
        return f"索引已刷新，共 {count} 个 Release 页", _list_releases(project_id)
    except RedmineError as exc:
        return f"刷新失败：{exc}", _list_releases(project_id)


def build_app() -> gr.Blocks:
    saved = get_saved_login()
    product_choices = list(PRODUCT_LINES.keys())
    today = date.today().isoformat()

    with gr.Blocks(title="Redmine 版本发布工具", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Redmine 固件版本发布工具")
        gr.Markdown("登录后选择项目，填写 Release 信息与固件附件，自动创建 Wiki 并同步上级索引。")

        with gr.Tab("连接设置"):
            base_url = gr.Textbox(
                label="Redmine 服务器地址",
                value=saved["base_url"],
                placeholder="例如：http://192.168.1.208:3000",
            )
            username = gr.Textbox(label="用户名", value=saved["username"])
            password = gr.Textbox(label="密码", type="password", value=saved["password"])
            remember = gr.Checkbox(label="记住账号密码（保存到本地文件）", value=saved["remember"])
            connect_btn = gr.Button("连接 / 保存", variant="primary")
            connect_status = gr.Textbox(label="状态", interactive=False)

        with gr.Tab("版本发布"):
            project_dd = gr.Dropdown(label="项目", choices=[], interactive=True)
            with gr.Row():
                reload_btn = gr.Button("刷新列表")
                refresh_index_btn = gr.Button("仅刷新 Release 索引")

            release_table = gr.Markdown(label="已有 Release 列表")

            gr.Markdown("---")
            gr.Markdown("### 发布 / 更新版本")

            edit_release_dd = gr.Dropdown(
                label="编辑已有版本（可选，选中后加载到下方表单）",
                choices=[],
                interactive=True,
            )
            existing_files_info = gr.Textbox(
                label="已有附件（编辑已有版本时自动加载）",
                value="（未选择已有版本）",
                lines=4,
                interactive=False,
            )
            with gr.Row():
                version_name = gr.Textbox(label="版本号", placeholder="V5.3.8.3")
                release_date = gr.Textbox(label="发布日期", value=today)
            commit = gr.Textbox(label="Commit", placeholder="git commit hash")
            product_line = gr.Dropdown(label="产品线", choices=product_choices, value=product_choices[0])
            changelog = gr.Textbox(
                label="变更说明（每行一条）",
                lines=6,
                placeholder="1. 修复 xxx\n2. 新增 yyy",
            )
            files = gr.File(label="新增固件附件 (.bin)", file_count="multiple", file_types=[".bin"])
            replace_attachments = gr.Checkbox(
                label="替换旧附件列表（不勾选则保留旧附件并追加新附件；不会删除 Redmine 项目文件里的旧文件）",
                value=False,
            )
            publish_btn = gr.Button("发布到 Redmine", variant="primary")
            publish_status = gr.Textbox(label="发布结果", interactive=False)

        # 若已保存凭据，启动时自动填充；用户点连接即可
        connect_btn.click(
            _connect,
            inputs=[base_url, username, password, remember],
            outputs=[connect_status, project_dd, project_dd],
        ).then(_list_releases, inputs=[project_dd], outputs=[release_table]).then(
            _release_choices, inputs=[project_dd], outputs=[edit_release_dd]
        )

        project_dd.change(
            _list_releases, inputs=[project_dd], outputs=[release_table]
        ).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])

        reload_btn.click(_list_releases, inputs=[project_dd], outputs=[release_table]).then(
            _release_choices, inputs=[project_dd], outputs=[edit_release_dd]
        )

        refresh_index_btn.click(_refresh_index, inputs=[project_dd], outputs=[publish_status, release_table])

        edit_release_dd.change(
            _load_release_to_form,
            inputs=[project_dd, edit_release_dd],
            outputs=[
                version_name,
                release_date,
                commit,
                product_line,
                changelog,
                existing_files_info,
                replace_attachments,
            ],
        )

        publish_btn.click(
            _publish,
            inputs=[
                project_dd,
                version_name,
                release_date,
                commit,
                product_line,
                changelog,
                files,
                replace_attachments,
                edit_release_dd,
            ],
            outputs=[publish_status, release_table],
        ).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])

    return app


def main() -> None:
    app = build_app()
    app.launch(server_name="127.0.0.1", inbrowser=True, show_error=True)


if __name__ == "__main__":
    main()
