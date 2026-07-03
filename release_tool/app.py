"""Gradio UI 入口。"""

from __future__ import annotations

import traceback
from datetime import date
import os
from pathlib import Path

import gradio as gr

from .config_store import allow_login_secret_storage, default_base_url, get_email_settings, get_last_project, get_saved_login, get_user_email_settings, set_last_project, store_login, store_user_email_settings
from .email_sender import EmailSendError, EmailSettings, build_release_email_body, build_release_email_subject, normalize_contact_lines, send_release_email, split_emails
from .index_sync import IndexSync
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import PRODUCT_LINES, ReleaseForm, format_release_files, parse_release_page, proj_tag_from_project
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text

RECENT_RELEASE_LIMIT = 10
BROWSER_LOGIN_STORE_JS = """
(session, authMode, username, password, apiKey, remember) => {
    const key = "redmine-release-tool-login-v1";
    try {
        if (!remember) {
            localStorage.removeItem(key);
            return [];
        }
        if (session && session.connected) {
            localStorage.setItem(key, JSON.stringify({
                auth_mode: authMode,
                username: username,
                password: password,
                api_key: apiKey
            }));
        }
    } catch (error) {
        console.warn("Failed to save login in browser", error);
    }
    return [];
}
"""
BROWSER_LOGIN_LOAD_JS = """
(authMode, username, password, apiKey, remember) => {
    const key = "redmine-release-tool-login-v1";
    try {
        const raw = localStorage.getItem(key);
        if (!raw) {
            return [authMode, username, password, apiKey, remember];
        }
        const data = JSON.parse(raw) || {};
        return [
            data.auth_mode || authMode,
            data.username || "",
            data.password || "",
            data.api_key || "",
            true
        ];
    } catch (error) {
        console.warn("Failed to load login from browser", error);
        return [authMode, username, password, apiKey, remember];
    }
}
"""


def _empty_session() -> dict:
    return {"connected": False, "base_url": "", "auth_mode": "password", "username": "", "password": "", "api_key": "", "projects": []}


def _user_key(base_url: str, login: str) -> str:
    return f"{base_url.rstrip('/')}|{login}"


def _session_user_key(session: dict | None) -> str:
    return (session or {}).get("user_key", "")


def _client(session: dict | None) -> RedmineClient | None:
    if not session or not session.get("connected"):
        return None
    return RedmineClient(
        session.get("base_url", ""),
        session.get("username", ""),
        session.get("password", ""),
        api_key=session.get("api_key", ""),
        auth_mode=session.get("auth_mode", "password"),
    )


def _project_dropdown(projects: list[dict], value: str | None = None) -> gr.Dropdown:
    choices = [(f"{p['name']} ({p['identifier']})", p["identifier"]) for p in projects]
    return gr.Dropdown(choices=choices, value=value)


def _default_project_id(projects: list[dict]) -> str | None:
    project_ids = [p["identifier"] for p in projects]
    last = get_last_project() if allow_login_secret_storage() else ""
    return last if last in project_ids else (project_ids[0] if project_ids else None)


def _default_product_line() -> str:
    return next(iter(PRODUCT_LINES), "")


def _filter_releases(releases: list[dict], product_line: str) -> list[dict]:
    if not product_line:
        return releases
    return [item for item in releases if item.get("product_line") == product_line]


def _page_visibility(connected: bool) -> tuple[dict, dict]:
    return gr.update(visible=not connected), gr.update(visible=connected)


def _connect(auth_mode: str, username: str, password: str, api_key: str, _browser_remember: bool) -> tuple:
    base_url = default_base_url()
    auth_mode = auth_mode or "password"
    username = (username or "").strip()
    api_key = (api_key or "").strip()
    login_visible, main_visible = _page_visibility(False)
    if not base_url:
        return "请先配置 REDMINE_BASE_URL", _empty_session(), login_visible, main_visible, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    if auth_mode == "api_key" and not api_key:
        return "请填写 API Key", _empty_session(), login_visible, main_visible, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    if auth_mode != "api_key" and (not username or not password):
        return "请填写用户名和密码", _empty_session(), login_visible, main_visible, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    try:
        client = RedmineClient(base_url, username, password, api_key=api_key, auth_mode=auth_mode)
        account = client.test_login()
        projects = client.list_projects()
        store_login(base_url, username, password, False, auth_mode=auth_mode, api_key=api_key)
        account_user = account.get("user", {})
        user_label = account_user.get("login", username or "api-key")
        session = {
            "connected": True,
            "base_url": base_url,
            "auth_mode": auth_mode,
            "username": username,
            "password": password,
            "api_key": api_key,
            "user_login": user_label,
            "user_key": _user_key(base_url, str(user_label)),
            "projects": projects,
        }
        default = _default_project_id(projects)
        mode_label = "API Key" if auth_mode == "api_key" else "用户名密码"
        login_hidden, main_shown = _page_visibility(True)
        return (
            f"已连接：{user_label}，方式：{mode_label}，共 {len(projects)} 个项目",
            session,
            login_hidden,
            main_shown,
            _project_dropdown(projects, default),
            _project_dropdown(projects, default),
            _project_dropdown(projects, default),
        )
    except RedmineError as exc:
        return f"连接失败：{exc}", _empty_session(), login_visible, main_visible, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    except Exception as exc:
        return f"连接失败：{exc}", _empty_session(), login_visible, main_visible, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[])


def _restore_connection(session: dict | None) -> tuple:
    projects = (session or {}).get("projects") or []
    if _client(session) and projects:
        default = _default_project_id(projects)
        default_line = _default_product_line()
        release_table = _list_releases(session, default or "", default_line)
        login_hidden, main_shown = _page_visibility(True)
        return (
            f"已恢复登录状态，共 {len(projects)} 个项目",
            session or _empty_session(),
            login_hidden,
            main_shown,
            _project_dropdown(projects, default),
            _project_dropdown(projects, default),
            _project_dropdown(projects, default),
            release_table,
            release_table,
            _release_choices(session, default or "", default_line),
        )

    saved = get_saved_login()
    auth_mode = saved["auth_mode"]
    has_secret = bool(saved["api_key"]) if auth_mode == "api_key" else bool(saved["username"] and saved["password"])
    if not saved["remember"] or not has_secret:
        login_visible, main_hidden = _page_visibility(False)
        return "", _empty_session(), login_visible, main_hidden, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), "", "", gr.Dropdown(choices=[])

    status, restored_session, login_update, main_update, project_dd, config_project_dd, edit_project_dd = _connect(
        auth_mode,
        saved["username"],
        saved["password"],
        saved["api_key"],
        saved["remember"],
    )
    projects = restored_session.get("projects") or []
    default = _default_project_id(projects)
    default_line = _default_product_line()
    release_table = _list_releases(restored_session, default or "", default_line) if _client(restored_session) else ""
    release_choices = _release_choices(restored_session, default or "", default_line) if _client(restored_session) else gr.Dropdown(choices=[])
    return status, restored_session, login_update, main_update, project_dd, config_project_dd, edit_project_dd, release_table, release_table, release_choices


def _notice_component_updates(data: dict) -> tuple:
    contacts_to = data.get("contacts_to", [])
    contacts_cc = data.get("contacts_cc", [])
    return (
        gr.update(value=data.get("smtp_host", "")),
        gr.update(value=data.get("smtp_port", 25)),
        gr.update(value=data.get("smtp_user", "")),
        gr.update(value=data.get("smtp_password", "")),
        gr.update(value=data.get("smtp_from", "")),
        gr.update(value=data.get("use_tls", False)),
        gr.update(value="\n".join(contacts_to)),
        gr.update(value="\n".join(contacts_cc)),
        gr.CheckboxGroup(choices=contacts_to, value=[]),
        gr.CheckboxGroup(choices=contacts_cc, value=[]),
        gr.CheckboxGroup(choices=contacts_to, value=[]),
        gr.CheckboxGroup(choices=contacts_cc, value=[]),
    )


def _load_notice_settings(session: dict | None) -> tuple:
    user_key = _session_user_key(session)
    data = get_user_email_settings(user_key) if user_key else get_email_settings()
    return _notice_component_updates(data)


def _save_notice_settings(session: dict | None, host: str, port: int | float | str, user: str, secret: str, sender: str, use_tls: bool, to_text: str, cc_text: str) -> tuple[str, gr.CheckboxGroup, gr.CheckboxGroup, gr.CheckboxGroup, gr.CheckboxGroup]:
    user_key = _session_user_key(session)
    if not user_key:
        return "请先登录 Redmine", gr.CheckboxGroup(choices=[]), gr.CheckboxGroup(choices=[]), gr.CheckboxGroup(choices=[]), gr.CheckboxGroup(choices=[])
    contacts_to = normalize_contact_lines(to_text or "")
    contacts_cc = normalize_contact_lines(cc_text or "")
    try:
        smtp_port = int(float(port or 25))
    except (TypeError, ValueError):
        smtp_port = 25
    store_user_email_settings(user_key, smtp_host=host, smtp_port=smtp_port, smtp_user=user, smtp_password=secret, smtp_from=sender, use_tls=use_tls, contacts_to=contacts_to, contacts_cc=contacts_cc)
    return (
        f"邮件设置已保存到当前用户：收件人 {len(contacts_to)} 个，抄送 {len(contacts_cc)} 个",
        gr.CheckboxGroup(choices=contacts_to, value=[]),
        gr.CheckboxGroup(choices=contacts_cc, value=[]),
        gr.CheckboxGroup(choices=contacts_to, value=[]),
        gr.CheckboxGroup(choices=contacts_cc, value=[]),
    )


def _list_releases(session: dict | None, project_id: str, product_line: str = "") -> str:
    client = _client(session)
    if not client:
        return "请先连接 Redmine"
    if not project_id:
        return "请选择项目"
    if allow_login_secret_storage():
        set_last_project(project_id)
    try:
        all_releases = ReleasePublisher(client).list_releases(project_id)
        releases = _filter_releases(all_releases, product_line)
        if not releases:
            return f"（暂无 {product_line} Release 页）" if product_line else "（暂无 Release 页）"
        visible_releases = releases[:RECENT_RELEASE_LIMIT]
        title = f"最近 {len(visible_releases)} / {len(releases)} 个 {product_line} Release" if product_line else f"最近 {len(visible_releases)} / {len(releases)} 个 Release"
        lines = [f"**{title}**", "", "| 版本 | 日期 | 产品线 | Wiki 页 | 摘要 |", "|---|---|---|---|---|"]
        for item in visible_releases:
            lines.append(f"| {item['version']} | {item['date']} | {item['product_line']} | {item['title']} | {item['summary'][:40]} |")
        return "\n".join(lines)
    except RedmineError as exc:
        return f"加载失败：{exc}"


def _load_release_to_form(session: dict | None, project_id: str, wiki_title: str) -> tuple:
    client = _client(session)
    default_line = list(PRODUCT_LINES.keys())[0]
    if not client or not project_id or not wiki_title:
        return "", "", "", default_line, "", "（未选择已有版本）", False
    page = client.get_wiki_page(project_id, wiki_title)
    if not page:
        return "", "", "", default_line, "", "（未找到版本页面）", False
    parsed = parse_release_page(wiki_title, page.get("text", ""))
    return parsed["version_name"], parsed["release_date"], parsed["commit"], parsed["product_line"], parsed["changelog"], format_release_files(parsed.get("files", [])), False


def _release_choices(session: dict | None, project_id: str, product_line: str = "") -> gr.Dropdown:
    client = _client(session)
    if not client or not project_id:
        return gr.Dropdown(choices=[])
    try:
        releases = _filter_releases(ReleasePublisher(client).list_releases(project_id), product_line)
        choices = [(f"{r['version']} — {r['title']}", r["title"]) for r in releases]
        return gr.Dropdown(choices=choices, value=None)
    except RedmineError:
        return gr.Dropdown(choices=[])


def _generate_config_template(project_id: str, template_key: str) -> tuple[str, str]:
    if not project_id:
        return "", "请选择项目"
    text = build_config_template(template_key or "single_list", project_id)
    ok, msg = validate_config_text(text)
    return text, f"已生成模板。{msg if ok else msg}"


def _load_config(session: dict | None, project_id: str) -> tuple[str, str]:
    client = _client(session)
    if not client:
        return "", "请先连接 Redmine"
    if not project_id:
        return "", "请选择项目"
    try:
        page = client.get_wiki_page(project_id, CONFIG_PAGE_TITLE)
        if not page:
            return "", f"未找到 {CONFIG_PAGE_TITLE}，请选择模板生成后保存。"
        text = page.get("text", "")
        ok, msg = validate_config_text(text)
        return text, msg if ok else f"已读取，但{msg}"
    except RedmineError as exc:
        return "", f"读取失败：{exc}"


def _check_config(config_text: str) -> str:
    ok, msg = validate_config_text(config_text or "")
    return msg if ok else msg


def _save_config(session: dict | None, project_id: str, config_text: str) -> str:
    client = _client(session)
    if not client:
        return "请先连接 Redmine"
    if not project_id:
        return "请选择项目"
    ok, msg = validate_config_text(config_text or "")
    if not ok:
        return msg
    try:
        client.put_wiki_page(project_id, CONFIG_PAGE_TITLE, config_text, "release tool config update")
        return f"已保存到 {CONFIG_PAGE_TITLE}。{msg}"
    except RedmineError as exc:
        return f"保存失败：{exc}"


def _publish(session: dict | None, project_id: str, version_name: str, release_date: str, commit: str, product_line: str, changelog: str, files: list, replace_attachments: bool, notice_enabled: bool, selected_to: list[str], selected_cc: list[str], edit_title: str, display_product_line: str | None = None) -> tuple[str, str]:
    list_product_line = display_product_line or product_line
    client = _client(session)
    if not client:
        return "请先连接 Redmine", _list_releases(session, project_id, list_product_line)
    if not project_id:
        return "请选择项目", ""
    if not version_name or not release_date or not commit:
        return "请填写版本号、日期和 Commit", _list_releases(session, project_id, list_product_line)
    items = [line.strip() for line in (changelog or "").splitlines() if line.strip()]
    if not items:
        return "请填写至少一条变更说明（每行一条）", _list_releases(session, project_id, list_product_line)

    file_rows: list[tuple[str, str, bytes]] = []
    for f in files or []:
        path = f if isinstance(f, str) else f.name
        p = Path(path)
        if p.exists():
            file_rows.append((p.name, "", p.read_bytes()))

    form = ReleaseForm(project_id=project_id, proj_tag=proj_tag_from_project(project_id, edit_title or None), version_name=version_name.strip(), release_date=release_date.strip(), commit=commit.strip(), product_line=product_line, changelog_items=items, files=file_rows, wiki_title=edit_title or None, replace_attachments=bool(replace_attachments))

    try:
        title = ReleasePublisher(client).publish(form)
        if edit_title and replace_attachments:
            note = "发布成功（已替换 Wiki 中的附件列表，旧项目文件未删除）"
        elif edit_title and file_rows:
            note = "发布成功（已保留旧附件并追加新附件）"
        elif edit_title:
            note = "发布成功（已保留旧附件）"
        else:
            note = "发布成功"
        if notice_enabled:
            note += "\n" + _send_notice(session, client, project_id, title, version_name.strip(), release_date.strip(), commit.strip(), product_line, items, file_rows, selected_to, selected_cc)
        return f"{note}：{title}", _list_releases(session, project_id, list_product_line)
    except RedmineError as exc:
        return f"发布失败：{exc}", _list_releases(session, project_id, list_product_line)
    except Exception as exc:
        return f"发布失败：{exc}\n{traceback.format_exc()}", _list_releases(session, project_id, list_product_line)


def _send_notice(session: dict | None, client: RedmineClient, project_id: str, wiki_title: str, version_name: str, release_date: str, commit: str, product_line: str, items: list[str], file_rows: list[tuple[str, str, bytes]], selected_to: list[str], selected_cc: list[str]) -> str:
    data = get_user_email_settings(_session_user_key(session))
    settings = EmailSettings(smtp_host=data["smtp_host"], smtp_port=data["smtp_port"], smtp_user=data["smtp_user"], smtp_password=data["smtp_password"], smtp_from=data["smtp_from"], use_tls=data["use_tls"])
    to_addrs = split_emails(selected_to)
    cc_addrs = split_emails(selected_cc)
    subject = build_release_email_subject(project_id, version_name, product_line)
    body = build_release_email_body(base_url=client.base_url, project_id=project_id, wiki_title=wiki_title, version_name=version_name, release_date=release_date, commit=commit, product_line=product_line, changelog_items=items, attachment_names=[name for name, _desc, _content in file_rows])
    try:
        send_release_email(settings, to_addrs=to_addrs, cc_addrs=cc_addrs, subject=subject, body=body, attachments=file_rows)
        return f"邮件已发送：收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个，附件 {len(file_rows)} 个"
    except EmailSendError as exc:
        return f"邮件发送失败：{exc}"


def _refresh_index(session: dict | None, project_id: str, product_line: str = "") -> tuple[str, str]:
    client = _client(session)
    if not client:
        return "请先连接 Redmine", ""
    if not project_id:
        return "请选择项目", ""
    try:
        count = IndexSync(client, project_id).refresh_all()
        return f"索引已刷新，共 {count} 个 Release 页", _list_releases(session, project_id, product_line)
    except RedmineError as exc:
        return f"刷新失败：{exc}", _list_releases(session, project_id, product_line)


def build_app() -> gr.Blocks:
    saved = get_saved_login()
    notice = get_email_settings()
    product_choices = list(PRODUCT_LINES.keys())
    today = date.today().isoformat()
    contact_to_choices = notice["contacts_to"]
    contact_cc_choices = notice["contacts_cc"]

    with gr.Blocks(title="Redmine 版本发布工具", theme=gr.themes.Soft()) as app:
        session_state = gr.State(_empty_session())

        with gr.Column(visible=True) as login_panel:
            gr.Markdown("# Redmine 固件版本发布工具")
            gr.Markdown("登录 Redmine 后进入发布工具。")
            auth_mode = gr.Radio(label="登录方式", choices=[("用户名密码", "password"), ("API Key", "api_key")], value=saved["auth_mode"])
            username = gr.Textbox(label="用户名", value=saved["username"])
            password = gr.Textbox(label="密码", type="password", value=saved["password"])
            api_key = gr.Textbox(label="API Key", type="password", value=saved["api_key"])
            remember = gr.Checkbox(label="在本机浏览器记住账号密码", value=saved["remember"])
            connect_btn = gr.Button("登录", variant="primary")
            connect_status = gr.Textbox(label="登录状态", interactive=False)

        with gr.Column(visible=False) as main_panel:
            gr.Markdown("# Redmine 固件版本发布工具")
            with gr.Tabs():
                with gr.Tab("结构管理"):
                    config_project_dd = gr.Dropdown(label="项目", choices=[], interactive=True)
                    template_dd = gr.Dropdown(label="结构模板", choices=TEMPLATE_CHOICES, value="single_list")
                    with gr.Row():
                        gen_config_btn = gr.Button("生成模板")
                        load_config_btn = gr.Button("读取当前配置")
                        check_config_btn = gr.Button("检测配置")
                        save_config_btn = gr.Button("保存到项目 Wiki", variant="primary")
                    config_text = gr.Textbox(label=f"{CONFIG_PAGE_TITLE} 内容", lines=22)
                    config_status = gr.Textbox(label="结构管理状态", interactive=False)

                with gr.Tab("邮件设置"):
                    with gr.Row():
                        notice_host = gr.Textbox(label="SMTP 服务器", value=notice["smtp_host"])
                        notice_port = gr.Number(label="SMTP 端口", value=notice["smtp_port"], precision=0)
                    with gr.Row():
                        notice_user = gr.Textbox(label="SMTP 用户名", value=notice["smtp_user"])
                        notice_secret = gr.Textbox(label="SMTP 密钥", type="password", value=notice["smtp_password"])
                    notice_sender = gr.Textbox(label="发件人", value=notice["smtp_from"])
                    notice_tls = gr.Checkbox(label="使用 STARTTLS；端口 465 自动使用 SSL", value=notice["use_tls"])
                    contacts_to_text = gr.Textbox(label="常用收件人（输入后保存，再到发布页选择）", value="\n".join(contact_to_choices), lines=4)
                    contacts_cc_text = gr.Textbox(label="常用抄送（输入后保存，再到发布页选择）", value="\n".join(contact_cc_choices), lines=4)
                    save_notice_btn = gr.Button("保存邮件设置", variant="primary")
                    notice_status = gr.Textbox(label="邮件设置状态", interactive=False)

                with gr.Tab("版本发布"):
                    project_dd = gr.Dropdown(label="项目", choices=[], interactive=True)
                    product_line = gr.Dropdown(label="产品线", choices=product_choices, value=product_choices[0])
                    with gr.Row():
                        reload_btn = gr.Button("刷新列表")
                        refresh_index_btn = gr.Button("仅刷新 Release 索引")
                    release_table = gr.Markdown(label="已有 Release 列表")
                    gr.Markdown("---")
                    gr.Markdown("### 发布新版本")
                    with gr.Row():
                        version_name = gr.Textbox(label="版本号", placeholder="V5.3.8.3")
                        release_date = gr.Textbox(label="发布日期", value=today)
                    commit = gr.Textbox(label="Commit", placeholder="git commit hash")
                    changelog = gr.Textbox(label="变更说明（每行一条）", lines=6, placeholder="1. 修复 xxx\n2. 新增 yyy")
                    files = gr.File(label="固件附件 (.bin)", file_count="multiple", file_types=[".bin"])
                    gr.Markdown("### 发布邮件（可选）")
                    notice_enabled = gr.Checkbox(label="发布成功后发送邮件", value=False)
                    selected_to = gr.CheckboxGroup(label="选择收件人", choices=contact_to_choices)
                    selected_cc = gr.CheckboxGroup(label="选择抄送", choices=contact_cc_choices)
                    gr.Markdown("邮件会包含版本信息、Wiki 链接、项目文件链接，并附加本次选择的固件文件。")
                    publish_btn = gr.Button("发布到 Redmine", variant="primary")
                    publish_status = gr.Textbox(label="发布结果", interactive=False)
                    new_replace_attachments = gr.State(False)
                    new_edit_title = gr.State("")

                with gr.Tab("版本编辑"):
                    edit_project_dd = gr.Dropdown(label="项目", choices=[], interactive=True)
                    edit_filter_product_line = gr.Dropdown(label="筛选产品线", choices=product_choices, value=product_choices[0])
                    with gr.Row():
                        edit_reload_btn = gr.Button("刷新列表")
                        edit_refresh_index_btn = gr.Button("仅刷新 Release 索引")
                    edit_release_table = gr.Markdown(label="已有 Release 列表")
                    edit_release_dd = gr.Dropdown(label="选择要编辑的版本", choices=[], interactive=True)
                    existing_files_info = gr.Textbox(label="已有附件", value="（未选择已有版本）", lines=4, interactive=False)
                    with gr.Row():
                        edit_version_name = gr.Textbox(label="版本号", placeholder="V5.3.8.3")
                        edit_release_date = gr.Textbox(label="发布日期", value=today)
                    edit_commit = gr.Textbox(label="Commit", placeholder="git commit hash")
                    edit_product_line = gr.Dropdown(label="版本产品线", choices=product_choices, value=product_choices[0])
                    edit_changelog = gr.Textbox(label="变更说明（每行一条）", lines=6, placeholder="1. 修复 xxx\n2. 新增 yyy")
                    edit_files = gr.File(label="新增固件附件 (.bin)", file_count="multiple", file_types=[".bin"])
                    edit_replace_attachments = gr.Checkbox(label="替换旧附件列表（不勾选则保留旧附件并追加新附件；不会删除 Redmine 项目文件里的旧文件）", value=False)
                    gr.Markdown("### 发布邮件（可选）")
                    edit_notice_enabled = gr.Checkbox(label="更新成功后发送邮件", value=False)
                    edit_selected_to = gr.CheckboxGroup(label="选择收件人", choices=contact_to_choices)
                    edit_selected_cc = gr.CheckboxGroup(label="选择抄送", choices=contact_cc_choices)
                    edit_publish_btn = gr.Button("更新到 Redmine", variant="primary")
                    edit_publish_status = gr.Textbox(label="更新结果", interactive=False)

        notice_setting_outputs = [notice_host, notice_port, notice_user, notice_secret, notice_sender, notice_tls, contacts_to_text, contacts_cc_text, selected_to, selected_cc, edit_selected_to, edit_selected_cc]

        connect_btn.click(_connect, inputs=[auth_mode, username, password, api_key, remember], outputs=[connect_status, session_state, login_panel, main_panel, project_dd, config_project_dd, edit_project_dd]).then(_load_notice_settings, inputs=[session_state], outputs=notice_setting_outputs).then(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table]).then(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd]).then(fn=None, inputs=[session_state, auth_mode, username, password, api_key, remember], outputs=[], js=BROWSER_LOGIN_STORE_JS)
        gen_config_btn.click(_generate_config_template, inputs=[config_project_dd, template_dd], outputs=[config_text, config_status])
        load_config_btn.click(_load_config, inputs=[session_state, config_project_dd], outputs=[config_text, config_status])
        check_config_btn.click(_check_config, inputs=[config_text], outputs=[config_status])
        save_config_btn.click(_save_config, inputs=[session_state, config_project_dd, config_text], outputs=[config_status])
        save_notice_btn.click(_save_notice_settings, inputs=[session_state, notice_host, notice_port, notice_user, notice_secret, notice_sender, notice_tls, contacts_to_text, contacts_cc_text], outputs=[notice_status, selected_to, selected_cc, edit_selected_to, edit_selected_cc])
        project_dd.change(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        product_line.change(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        reload_btn.click(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        refresh_index_btn.click(_refresh_index, inputs=[session_state, project_dd, product_line], outputs=[publish_status, release_table])
        publish_btn.click(_publish, inputs=[session_state, project_dd, version_name, release_date, commit, product_line, changelog, files, new_replace_attachments, notice_enabled, selected_to, selected_cc, new_edit_title], outputs=[publish_status, release_table])
        edit_project_dd.change(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_filter_product_line.change(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_reload_btn.click(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_refresh_index_btn.click(_refresh_index, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_publish_status, edit_release_table])
        edit_release_dd.change(_load_release_to_form, inputs=[session_state, edit_project_dd, edit_release_dd], outputs=[edit_version_name, edit_release_date, edit_commit, edit_product_line, edit_changelog, existing_files_info, edit_replace_attachments])
        edit_publish_btn.click(_publish, inputs=[session_state, edit_project_dd, edit_version_name, edit_release_date, edit_commit, edit_product_line, edit_changelog, edit_files, edit_replace_attachments, edit_notice_enabled, edit_selected_to, edit_selected_cc, edit_release_dd, edit_filter_product_line], outputs=[edit_publish_status, edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        app.load(_restore_connection, inputs=[session_state], outputs=[connect_status, session_state, login_panel, main_panel, project_dd, config_project_dd, edit_project_dd, release_table, edit_release_table, edit_release_dd]).then(_load_notice_settings, inputs=[session_state], outputs=notice_setting_outputs)
        app.load(fn=None, inputs=[auth_mode, username, password, api_key, remember], outputs=[auth_mode, username, password, api_key, remember], js=BROWSER_LOGIN_LOAD_JS)

    return app


def _launch_auth() -> tuple[str, str] | None:
    value = os.environ.get("RELEASE_TOOL_AUTH", "").strip()
    if not value:
        return None
    user, sep, password = value.partition(":")
    if not sep or not user or not password:
        raise ValueError("RELEASE_TOOL_AUTH 格式应为 username:password")
    return user, password


def main() -> None:
    app = build_app()
    host = os.environ.get("RELEASE_TOOL_HOST", "127.0.0.1")
    port = int(os.environ.get("RELEASE_TOOL_PORT", "7860"))
    app.launch(server_name=host, server_port=port, auth=_launch_auth(), inbrowser=host in {"127.0.0.1", "localhost"}, show_error=True)


if __name__ == "__main__":
    main()
