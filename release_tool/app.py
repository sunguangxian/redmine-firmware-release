"""Gradio UI 入口。"""

from __future__ import annotations

import traceback
from datetime import date
from pathlib import Path

import gradio as gr

from .config_store import get_email_settings, get_last_project, get_saved_login, set_last_project, store_email_settings, store_login
from .email_sender import EmailSendError, EmailSettings, build_release_email_body, build_release_email_subject, normalize_contact_lines, send_release_email, split_emails
from .index_sync import IndexSync
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import PRODUCT_LINES, ReleaseForm, format_release_files, parse_release_page, proj_tag_from_project
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text

_session: dict = {"client": None, "projects": []}


def _client() -> RedmineClient | None:
    return _session.get("client")


def _project_dropdowns(projects: list[dict], value: str | None = None) -> tuple[gr.Dropdown, gr.Dropdown]:
    choices = [(f"{p['name']} ({p['identifier']})", p["identifier"]) for p in projects]
    return gr.Dropdown(choices=choices, value=value), gr.Dropdown(choices=choices, value=value)


def _connect(auth_mode: str, base_url: str, username: str, password: str, api_key: str, remember: bool) -> tuple[str, gr.Dropdown, gr.Dropdown]:
    base_url = (base_url or "").strip().rstrip("/")
    auth_mode = auth_mode or "password"
    username = (username or "").strip()
    api_key = (api_key or "").strip()
    if not base_url:
        return "请填写 Redmine 地址", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    if auth_mode == "api_key" and not api_key:
        return "请填写 API Key", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    if auth_mode != "api_key" and (not username or not password):
        return "请填写用户名和密码", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    try:
        client = RedmineClient(base_url, username, password, api_key=api_key, auth_mode=auth_mode)
        account = client.test_login()
        projects = client.list_projects()
        _session["client"] = client
        _session["projects"] = projects
        store_login(base_url, username, password, remember, auth_mode=auth_mode, api_key=api_key)
        choices = [(f"{p['name']} ({p['identifier']})", p["identifier"]) for p in projects]
        last = get_last_project()
        default = last if last in [c[1] for c in choices] else (choices[0][1] if choices else None)
        user_label = account.get("user", {}).get("login", username or "api-key")
        mode_label = "API Key" if auth_mode == "api_key" else "用户名密码"
        return f"已连接：{user_label}，方式：{mode_label}，共 {len(projects)} 个项目", *_project_dropdowns(projects, default)
    except RedmineError as exc:
        _session["client"] = None
        return f"连接失败：{exc}", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])
    except Exception as exc:
        _session["client"] = None
        return f"连接失败：{exc}", gr.Dropdown(choices=[]), gr.Dropdown(choices=[])


def _save_notice_settings(host: str, port: int | float | str, user: str, secret: str, sender: str, use_tls: bool, to_text: str, cc_text: str) -> tuple[str, gr.CheckboxGroup, gr.CheckboxGroup]:
    contacts_to = normalize_contact_lines(to_text or "")
    contacts_cc = normalize_contact_lines(cc_text or "")
    try:
        smtp_port = int(float(port or 25))
    except (TypeError, ValueError):
        smtp_port = 25
    store_email_settings(smtp_host=host, smtp_port=smtp_port, smtp_user=user, smtp_password=secret, smtp_from=sender, use_tls=use_tls, contacts_to=contacts_to, contacts_cc=contacts_cc)
    return f"邮件设置已保存：收件人 {len(contacts_to)} 个，抄送 {len(contacts_cc)} 个", gr.CheckboxGroup(choices=contacts_to, value=[]), gr.CheckboxGroup(choices=contacts_cc, value=[])


def _list_releases(project_id: str) -> str:
    client = _client()
    if not client:
        return "请先连接 Redmine"
    if not project_id:
        return "请选择项目"
    set_last_project(project_id)
    try:
        releases = ReleasePublisher(client).list_releases(project_id)
        if not releases:
            return "（暂无 Release 页）"
        lines = ["| 版本 | 日期 | 产品线 | Wiki 页 | 摘要 |", "|---|---|---|---|---|"]
        for item in releases:
            lines.append(f"| {item['version']} | {item['date']} | {item['product_line']} | {item['title']} | {item['summary'][:40]} |")
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
    return parsed["version_name"], parsed["release_date"], parsed["commit"], parsed["product_line"], parsed["changelog"], format_release_files(parsed.get("files", [])), False


def _release_choices(project_id: str) -> gr.Dropdown:
    client = _client()
    if not client or not project_id:
        return gr.Dropdown(choices=[])
    try:
        releases = ReleasePublisher(client).list_releases(project_id)
        return gr.Dropdown(choices=[(f"{r['version']} — {r['title']}", r["title"]) for r in releases])
    except RedmineError:
        return gr.Dropdown(choices=[])


def _generate_config_template(project_id: str, template_key: str) -> tuple[str, str]:
    if not project_id:
        return "", "请选择项目"
    text = build_config_template(template_key or "single_list", project_id)
    ok, msg = validate_config_text(text)
    return text, f"已生成模板。{msg if ok else msg}"


def _load_config(project_id: str) -> tuple[str, str]:
    client = _client()
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


def _save_config(project_id: str, config_text: str) -> str:
    client = _client()
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


def _publish(project_id: str, version_name: str, release_date: str, commit: str, product_line: str, changelog: str, files: list, replace_attachments: bool, notice_enabled: bool, selected_to: list[str], selected_cc: list[str], edit_title: str) -> tuple[str, str]:
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
            note += "\n" + _send_notice(client, project_id, title, version_name.strip(), release_date.strip(), commit.strip(), product_line, items, file_rows, selected_to, selected_cc)
        return f"{note}：{title}", _list_releases(project_id)
    except RedmineError as exc:
        return f"发布失败：{exc}", _list_releases(project_id)
    except Exception as exc:
        return f"发布失败：{exc}\n{traceback.format_exc()}", _list_releases(project_id)


def _send_notice(client: RedmineClient, project_id: str, wiki_title: str, version_name: str, release_date: str, commit: str, product_line: str, items: list[str], file_rows: list[tuple[str, str, bytes]], selected_to: list[str], selected_cc: list[str]) -> str:
    data = get_email_settings()
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
    notice = get_email_settings()
    product_choices = list(PRODUCT_LINES.keys())
    today = date.today().isoformat()
    contact_to_choices = notice["contacts_to"]
    contact_cc_choices = notice["contacts_cc"]

    with gr.Blocks(title="Redmine 版本发布工具", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Redmine 固件版本发布工具")
        gr.Markdown("登录后选择项目，填写 Release 信息与固件附件，自动创建 Wiki 并同步上级索引。")

        with gr.Tab("连接设置"):
            auth_mode = gr.Radio(label="登录方式", choices=[("用户名密码", "password"), ("API Key", "api_key")], value=saved["auth_mode"])
            base_url = gr.Textbox(label="Redmine 服务器地址", value=saved["base_url"], placeholder="例如：http://192.168.1.208:3000")
            username = gr.Textbox(label="用户名", value=saved["username"])
            password = gr.Textbox(label="密码", type="password", value=saved["password"])
            api_key = gr.Textbox(label="API Key", type="password", value=saved["api_key"])
            remember = gr.Checkbox(label="记住登录信息（保存到本地文件）", value=saved["remember"])
            connect_btn = gr.Button("连接 / 保存", variant="primary")
            connect_status = gr.Textbox(label="状态", interactive=False)

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
            with gr.Row():
                reload_btn = gr.Button("刷新列表")
                refresh_index_btn = gr.Button("仅刷新 Release 索引")
            release_table = gr.Markdown(label="已有 Release 列表")
            gr.Markdown("---")
            gr.Markdown("### 发布 / 更新版本")
            edit_release_dd = gr.Dropdown(label="编辑已有版本（可选，选中后加载到下方表单）", choices=[], interactive=True)
            existing_files_info = gr.Textbox(label="已有附件（编辑已有版本时自动加载）", value="（未选择已有版本）", lines=4, interactive=False)
            with gr.Row():
                version_name = gr.Textbox(label="版本号", placeholder="V5.3.8.3")
                release_date = gr.Textbox(label="发布日期", value=today)
            commit = gr.Textbox(label="Commit", placeholder="git commit hash")
            product_line = gr.Dropdown(label="产品线", choices=product_choices, value=product_choices[0])
            changelog = gr.Textbox(label="变更说明（每行一条）", lines=6, placeholder="1. 修复 xxx\n2. 新增 yyy")
            files = gr.File(label="新增固件附件 (.bin)", file_count="multiple", file_types=[".bin"])
            replace_attachments = gr.Checkbox(label="替换旧附件列表（不勾选则保留旧附件并追加新附件；不会删除 Redmine 项目文件里的旧文件）", value=False)
            gr.Markdown("### 发布邮件（可选）")
            notice_enabled = gr.Checkbox(label="发布成功后发送邮件", value=False)
            selected_to = gr.CheckboxGroup(label="选择收件人", choices=contact_to_choices)
            selected_cc = gr.CheckboxGroup(label="选择抄送", choices=contact_cc_choices)
            gr.Markdown("邮件会包含版本信息、Wiki 链接、项目文件链接，并附加本次选择的固件文件。")
            publish_btn = gr.Button("发布到 Redmine", variant="primary")
            publish_status = gr.Textbox(label="发布结果", interactive=False)

        connect_btn.click(_connect, inputs=[auth_mode, base_url, username, password, api_key, remember], outputs=[connect_status, project_dd, config_project_dd]).then(_list_releases, inputs=[project_dd], outputs=[release_table]).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])
        gen_config_btn.click(_generate_config_template, inputs=[config_project_dd, template_dd], outputs=[config_text, config_status])
        load_config_btn.click(_load_config, inputs=[config_project_dd], outputs=[config_text, config_status])
        check_config_btn.click(_check_config, inputs=[config_text], outputs=[config_status])
        save_config_btn.click(_save_config, inputs=[config_project_dd, config_text], outputs=[config_status])
        save_notice_btn.click(_save_notice_settings, inputs=[notice_host, notice_port, notice_user, notice_secret, notice_sender, notice_tls, contacts_to_text, contacts_cc_text], outputs=[notice_status, selected_to, selected_cc])
        project_dd.change(_list_releases, inputs=[project_dd], outputs=[release_table]).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])
        reload_btn.click(_list_releases, inputs=[project_dd], outputs=[release_table]).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])
        refresh_index_btn.click(_refresh_index, inputs=[project_dd], outputs=[publish_status, release_table])
        edit_release_dd.change(_load_release_to_form, inputs=[project_dd, edit_release_dd], outputs=[version_name, release_date, commit, product_line, changelog, existing_files_info, replace_attachments])
        publish_btn.click(_publish, inputs=[project_dd, version_name, release_date, commit, product_line, changelog, files, replace_attachments, notice_enabled, selected_to, selected_cc, edit_release_dd], outputs=[publish_status, release_table]).then(_release_choices, inputs=[project_dd], outputs=[edit_release_dd])

    return app


def main() -> None:
    app = build_app()
    app.launch(server_name="127.0.0.1", inbrowser=True, show_error=True)


if __name__ == "__main__":
    main()
