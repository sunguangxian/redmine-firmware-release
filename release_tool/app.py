"""Gradio UI 入口。"""

from __future__ import annotations

import os
import traceback
from datetime import date
from pathlib import Path

import gradio as gr

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    allow_login_secret_storage,
    default_base_url,
    get_email_server_settings,
    get_internal_contact_settings,
    get_last_project,
    get_saved_login,
    get_user_external_email_settings,
    set_last_project,
    store_email_server_settings,
    store_internal_contact_settings,
    store_login,
    store_user_external_email_settings,
)
from .email_sender import (
    EmailSendError,
    EmailSettings,
    build_release_email_body,
    build_release_email_subject,
    normalize_contact_lines,
    send_release_email,
    split_emails,
)
from .index_sync import IndexSync
from .publisher import ReleasePublisher
from .redmine_api import RedmineClient, RedmineError
from .release_page import PRODUCT_LINES, ReleaseForm, format_release_files, parse_release_page, proj_tag_from_project
from .wiki_config import CONFIG_PAGE_TITLE
from .wiki_templates import TEMPLATE_CHOICES, build_config_template, validate_config_text

RECENT_RELEASE_LIMIT = 10
MAIL_SCOPE_CHOICES = [("内网邮件", MAIL_SCOPE_INTERNAL), ("外网邮件", MAIL_SCOPE_EXTERNAL)]

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
    return {
        "connected": False,
        "base_url": "",
        "auth_mode": "password",
        "username": "",
        "password": "",
        "api_key": "",
        "user_login": "",
        "user_key": "",
        "is_admin": False,
        "projects": [],
    }


def _user_key(base_url: str, login: str) -> str:
    return f"{base_url.rstrip('/')}|{login}"


def _session_user_key(session: dict | None) -> str:
    return (session or {}).get("user_key", "")


def _session_is_admin(session: dict | None) -> bool:
    return bool((session or {}).get("is_admin", False))


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


def _normalize_mail_scope(scope: str | None) -> str:
    return scope if scope in {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL} else MAIL_SCOPE_INTERNAL


def _mail_scope_label(scope: str | None) -> str:
    return "外网" if _normalize_mail_scope(scope) == MAIL_SCOPE_EXTERNAL else "内网"


def _to_int_port(port: int | float | str, default: int = 25) -> int:
    try:
        return int(float(port or default))
    except (TypeError, ValueError):
        return default


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
        is_admin = bool(account_user.get("admin", False))
        session = {
            "connected": True,
            "base_url": base_url,
            "auth_mode": auth_mode,
            "username": username,
            "password": password,
            "api_key": api_key,
            "user_login": user_label,
            "user_key": _user_key(base_url, str(user_label)),
            "is_admin": is_admin,
            "projects": projects,
        }
        default = _default_project_id(projects)
        mode_label = "API Key" if auth_mode == "api_key" else "用户名密码"
        role_label = "管理员" if is_admin else "普通用户"
        login_hidden, main_shown = _page_visibility(True)
        return (
            f"已连接：{user_label}，方式：{mode_label}，角色：{role_label}，共 {len(projects)} 个项目",
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
        role_label = "管理员" if _session_is_admin(session) else "普通用户"
        return (
            f"已恢复登录状态，角色：{role_label}，共 {len(projects)} 个项目",
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


def _contact_lists_for_scope(session: dict | None, mail_scope: str | None) -> tuple[list[str], list[str]]:
    scope = _normalize_mail_scope(mail_scope)
    if scope == MAIL_SCOPE_INTERNAL:
        contacts = get_internal_contact_settings()
    else:
        contacts = get_user_external_email_settings(_session_user_key(session))
    return contacts.get("contacts_to", []), contacts.get("contacts_cc", [])


def _checkbox_updates_for_scope(session: dict | None, mail_scope: str | None) -> tuple[gr.CheckboxGroup, gr.CheckboxGroup]:
    contacts_to, contacts_cc = _contact_lists_for_scope(session, mail_scope)
    return gr.CheckboxGroup(choices=contacts_to, value=[]), gr.CheckboxGroup(choices=contacts_cc, value=[])


def _release_scope_changed(session: dict | None, mail_scope: str | None) -> tuple[gr.CheckboxGroup, gr.CheckboxGroup]:
    return _checkbox_updates_for_scope(session, mail_scope)


def _notice_contact_outputs(session: dict | None, release_scope: str | None, edit_scope: str | None) -> tuple:
    release_to, release_cc = _checkbox_updates_for_scope(session, release_scope)
    edit_to, edit_cc = _checkbox_updates_for_scope(session, edit_scope)
    return release_to, release_cc, edit_to, edit_cc


def _notice_component_updates(session: dict | None, release_scope: str | None, edit_scope: str | None) -> tuple:
    internal_server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
    external_server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    internal_contacts = get_internal_contact_settings()
    external_user = get_user_external_email_settings(_session_user_key(session))
    return (
        gr.update(visible=_session_is_admin(session)),
        gr.update(value=internal_server["smtp_host"]),
        gr.update(value=internal_server["smtp_port"]),
        gr.update(value=internal_server["smtp_from"]),
        gr.update(value=internal_server["use_tls"]),
        gr.update(value=external_server["smtp_host"]),
        gr.update(value=external_server["smtp_port"]),
        gr.update(value=external_server["use_tls"]),
        gr.update(value="\n".join(internal_contacts["contacts_to"])),
        gr.update(value="\n".join(internal_contacts["contacts_cc"])),
        gr.update(value=external_user["smtp_user"]),
        gr.update(value=external_user["smtp_password"]),
        gr.update(value=external_user["smtp_from"]),
        gr.update(value="\n".join(external_user["contacts_to"])),
        gr.update(value="\n".join(external_user["contacts_cc"])),
        *_notice_contact_outputs(session, release_scope, edit_scope),
    )


def _load_notice_settings(session: dict | None, release_scope: str | None = MAIL_SCOPE_INTERNAL, edit_scope: str | None = MAIL_SCOPE_INTERNAL) -> tuple:
    return _notice_component_updates(session, release_scope, edit_scope)


def _save_admin_notice_settings(
    session: dict | None,
    internal_host: str,
    internal_port: int | float | str,
    internal_sender: str,
    internal_use_tls: bool,
    external_host: str,
    external_port: int | float | str,
    external_use_tls: bool,
    internal_to_text: str,
    internal_cc_text: str,
    release_scope: str | None,
    edit_scope: str | None,
) -> tuple:
    if not _session_is_admin(session):
        return "只有 Redmine 管理员可以修改邮件服务器和内网联系人配置", *_notice_contact_outputs(session, release_scope, edit_scope)

    contacts_to = normalize_contact_lines(internal_to_text or "")
    contacts_cc = normalize_contact_lines(internal_cc_text or "")
    store_email_server_settings(
        MAIL_SCOPE_INTERNAL,
        smtp_host=internal_host,
        smtp_port=_to_int_port(internal_port),
        smtp_from=internal_sender,
        use_tls=internal_use_tls,
    )
    store_email_server_settings(
        MAIL_SCOPE_EXTERNAL,
        smtp_host=external_host,
        smtp_port=_to_int_port(external_port),
        smtp_from="",
        use_tls=external_use_tls,
    )
    store_internal_contact_settings(contacts_to=contacts_to, contacts_cc=contacts_cc)
    msg = f"管理员邮件配置已保存：内网收件人 {len(contacts_to)} 个，内网抄送 {len(contacts_cc)} 个"
    return msg, *_notice_contact_outputs(session, release_scope, edit_scope)


def _save_user_notice_settings(
    session: dict | None,
    external_user: str,
    external_secret: str,
    external_sender: str,
    external_to_text: str,
    external_cc_text: str,
    release_scope: str | None,
    edit_scope: str | None,
) -> tuple:
    user_key = _session_user_key(session)
    if not user_key:
        return "请先登录 Redmine", *_notice_contact_outputs(session, release_scope, edit_scope)

    contacts_to = normalize_contact_lines(external_to_text or "")
    contacts_cc = normalize_contact_lines(external_cc_text or "")
    store_user_external_email_settings(
        user_key,
        smtp_user=external_user,
        smtp_password=external_secret,
        smtp_from=external_sender,
        contacts_to=contacts_to,
        contacts_cc=contacts_cc,
    )
    msg = f"个人外网邮件设置已保存：外网收件人 {len(contacts_to)} 个，外网抄送 {len(contacts_cc)} 个"
    return msg, *_notice_contact_outputs(session, release_scope, edit_scope)


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


def _publish(
    session: dict | None,
    project_id: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog: str,
    files: list,
    replace_attachments: bool,
    notice_enabled: bool,
    mail_scope: str,
    selected_to: list[str],
    selected_cc: list[str],
    edit_title: str,
    display_product_line: str | None = None,
) -> tuple[str, str]:
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
            note += "\n" + _send_notice(
                session,
                client,
                project_id,
                title,
                version_name.strip(),
                release_date.strip(),
                commit.strip(),
                product_line,
                items,
                file_rows,
                mail_scope,
                selected_to,
                selected_cc,
            )
        return f"{note}：{title}", _list_releases(session, project_id, list_product_line)
    except RedmineError as exc:
        return f"发布失败：{exc}", _list_releases(session, project_id, list_product_line)
    except Exception as exc:
        return f"发布失败：{exc}\n{traceback.format_exc()}", _list_releases(session, project_id, list_product_line)


def _validate_selected_contacts(
    mail_scope: str,
    to_addrs: list[str],
    cc_addrs: list[str],
    contacts_to: list[str],
    contacts_cc: list[str],
) -> None:
    allowed = {item.lower() for item in split_emails(contacts_to, contacts_cc)}
    selected = {item.lower() for item in split_emails(to_addrs, cc_addrs)}
    invalid = sorted(selected - allowed)
    if invalid:
        label = _mail_scope_label(mail_scope)
        raise EmailSendError(f"{label}邮件包含不允许的联系人：{', '.join(invalid)}")


def _build_notice_settings(session: dict | None, mail_scope: str) -> tuple[EmailSettings, list[str], list[str]]:
    scope = _normalize_mail_scope(mail_scope)
    if scope == MAIL_SCOPE_INTERNAL:
        server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        contacts = get_internal_contact_settings()
        settings = EmailSettings(
            smtp_host=server["smtp_host"],
            smtp_port=server["smtp_port"],
            smtp_user="",
            smtp_password="",
            smtp_from=server["smtp_from"],
            use_tls=server["use_tls"],
        )
        return settings, contacts["contacts_to"], contacts["contacts_cc"]

    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    external_user = get_user_external_email_settings(_session_user_key(session))
    if not external_user["smtp_user"] or not external_user["smtp_password"]:
        raise EmailSendError("外网邮件请先在邮件设置中配置个人 SMTP 用户名和密码")
    settings = EmailSettings(
        smtp_host=server["smtp_host"],
        smtp_port=server["smtp_port"],
        smtp_user=external_user["smtp_user"],
        smtp_password=external_user["smtp_password"],
        smtp_from=external_user["smtp_from"],
        use_tls=server["use_tls"],
    )
    return settings, external_user["contacts_to"], external_user["contacts_cc"]


def _send_notice(
    session: dict | None,
    client: RedmineClient,
    project_id: str,
    wiki_title: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    items: list[str],
    file_rows: list[tuple[str, str, bytes]],
    mail_scope: str,
    selected_to: list[str],
    selected_cc: list[str],
) -> str:
    to_addrs = split_emails(selected_to)
    cc_addrs = split_emails(selected_cc)
    subject = build_release_email_subject(project_id, version_name, product_line)
    body = build_release_email_body(
        base_url=client.base_url,
        project_id=project_id,
        wiki_title=wiki_title,
        version_name=version_name,
        release_date=release_date,
        commit=commit,
        product_line=product_line,
        changelog_items=items,
        attachment_names=[name for name, _desc, _content in file_rows],
    )
    try:
        settings, contacts_to, contacts_cc = _build_notice_settings(session, mail_scope)
        _validate_selected_contacts(mail_scope, to_addrs, cc_addrs, contacts_to, contacts_cc)
        send_release_email(settings, to_addrs=to_addrs, cc_addrs=cc_addrs, subject=subject, body=body, attachments=file_rows)
        label = _mail_scope_label(mail_scope)
        return f"{label}邮件已发送：收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个，附件 {len(file_rows)} 个"
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
    internal_server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
    external_server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    internal_contacts = get_internal_contact_settings()
    external_user = get_user_external_email_settings("")
    product_choices = list(PRODUCT_LINES.keys())
    today = date.today().isoformat()
    default_scope = MAIL_SCOPE_INTERNAL
    contact_to_choices, contact_cc_choices = _contact_lists_for_scope(None, default_scope)

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
                    gr.Markdown("普通用户只能维护个人外网 SMTP 账号和外网联系人；邮件服务器和内网联系人仅 Redmine 管理员可修改。")
                    with gr.Group(visible=False) as admin_notice_group:
                        gr.Markdown("### 管理员配置")
                        gr.Markdown("#### 内网邮件服务器")
                        with gr.Row():
                            internal_notice_host = gr.Textbox(label="内网 SMTP 服务器", value=internal_server["smtp_host"])
                            internal_notice_port = gr.Number(label="内网 SMTP 端口", value=internal_server["smtp_port"], precision=0)
                        internal_notice_sender = gr.Textbox(label="内网发件人", value=internal_server["smtp_from"])
                        internal_notice_tls = gr.Checkbox(label="内网使用 STARTTLS；端口 465 自动使用 SSL", value=internal_server["use_tls"])
                        gr.Markdown("#### 外网邮件服务器")
                        with gr.Row():
                            external_notice_host = gr.Textbox(label="外网 SMTP 服务器", value=external_server["smtp_host"])
                            external_notice_port = gr.Number(label="外网 SMTP 端口", value=external_server["smtp_port"], precision=0)
                        external_notice_tls = gr.Checkbox(label="外网使用 STARTTLS；端口 465 自动使用 SSL", value=external_server["use_tls"])
                        gr.Markdown("#### 内网联系人")
                        internal_contacts_to_text = gr.Textbox(label="内网收件人（管理员维护）", value="\n".join(internal_contacts["contacts_to"]), lines=4)
                        internal_contacts_cc_text = gr.Textbox(label="内网抄送（管理员维护）", value="\n".join(internal_contacts["contacts_cc"]), lines=4)
                        save_admin_notice_btn = gr.Button("保存管理员邮件配置", variant="primary")

                    gr.Markdown("### 个人外网邮件账号和联系人")
                    with gr.Row():
                        external_notice_user = gr.Textbox(label="外网 SMTP 用户名", value=external_user["smtp_user"])
                        external_notice_secret = gr.Textbox(label="外网 SMTP 密码", type="password", value=external_user["smtp_password"])
                    external_notice_sender = gr.Textbox(label="外网发件人", value=external_user["smtp_from"])
                    external_contacts_to_text = gr.Textbox(label="外网收件人（个人维护）", value="\n".join(external_user["contacts_to"]), lines=4)
                    external_contacts_cc_text = gr.Textbox(label="外网抄送（个人维护）", value="\n".join(external_user["contacts_cc"]), lines=4)
                    save_user_notice_btn = gr.Button("保存个人外网邮件设置", variant="primary")
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
                    notice_scope = gr.Radio(label="邮件类型", choices=MAIL_SCOPE_CHOICES, value=default_scope)
                    selected_to = gr.CheckboxGroup(label="选择收件人", choices=contact_to_choices)
                    selected_cc = gr.CheckboxGroup(label="选择抄送", choices=contact_cc_choices)
                    gr.Markdown("邮件会包含版本信息、Wiki 链接、项目文件链接，并附加本次选择的固件文件。选择内网/外网后，只能选择对应类型的联系人。")
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
                    edit_notice_scope = gr.Radio(label="邮件类型", choices=MAIL_SCOPE_CHOICES, value=default_scope)
                    edit_selected_to = gr.CheckboxGroup(label="选择收件人", choices=contact_to_choices)
                    edit_selected_cc = gr.CheckboxGroup(label="选择抄送", choices=contact_cc_choices)
                    edit_publish_btn = gr.Button("更新到 Redmine", variant="primary")
                    edit_publish_status = gr.Textbox(label="更新结果", interactive=False)

        notice_setting_outputs = [
            admin_notice_group,
            internal_notice_host,
            internal_notice_port,
            internal_notice_sender,
            internal_notice_tls,
            external_notice_host,
            external_notice_port,
            external_notice_tls,
            internal_contacts_to_text,
            internal_contacts_cc_text,
            external_notice_user,
            external_notice_secret,
            external_notice_sender,
            external_contacts_to_text,
            external_contacts_cc_text,
            selected_to,
            selected_cc,
            edit_selected_to,
            edit_selected_cc,
        ]
        notice_contact_outputs = [selected_to, selected_cc, edit_selected_to, edit_selected_cc]

        connect_btn.click(
            _connect,
            inputs=[auth_mode, username, password, api_key, remember],
            outputs=[connect_status, session_state, login_panel, main_panel, project_dd, config_project_dd, edit_project_dd],
        ).then(
            _load_notice_settings,
            inputs=[session_state, notice_scope, edit_notice_scope],
            outputs=notice_setting_outputs,
        ).then(
            _list_releases,
            inputs=[session_state, project_dd, product_line],
            outputs=[release_table],
        ).then(
            _list_releases,
            inputs=[session_state, edit_project_dd, edit_filter_product_line],
            outputs=[edit_release_table],
        ).then(
            _release_choices,
            inputs=[session_state, edit_project_dd, edit_filter_product_line],
            outputs=[edit_release_dd],
        ).then(fn=None, inputs=[session_state, auth_mode, username, password, api_key, remember], outputs=[], js=BROWSER_LOGIN_STORE_JS)

        gen_config_btn.click(_generate_config_template, inputs=[config_project_dd, template_dd], outputs=[config_text, config_status])
        load_config_btn.click(_load_config, inputs=[session_state, config_project_dd], outputs=[config_text, config_status])
        check_config_btn.click(_check_config, inputs=[config_text], outputs=[config_status])
        save_config_btn.click(_save_config, inputs=[session_state, config_project_dd, config_text], outputs=[config_status])
        save_admin_notice_btn.click(
            _save_admin_notice_settings,
            inputs=[
                session_state,
                internal_notice_host,
                internal_notice_port,
                internal_notice_sender,
                internal_notice_tls,
                external_notice_host,
                external_notice_port,
                external_notice_tls,
                internal_contacts_to_text,
                internal_contacts_cc_text,
                notice_scope,
                edit_notice_scope,
            ],
            outputs=[notice_status, *notice_contact_outputs],
        )
        save_user_notice_btn.click(
            _save_user_notice_settings,
            inputs=[
                session_state,
                external_notice_user,
                external_notice_secret,
                external_notice_sender,
                external_contacts_to_text,
                external_contacts_cc_text,
                notice_scope,
                edit_notice_scope,
            ],
            outputs=[notice_status, *notice_contact_outputs],
        )
        notice_scope.change(_release_scope_changed, inputs=[session_state, notice_scope], outputs=[selected_to, selected_cc])
        edit_notice_scope.change(_release_scope_changed, inputs=[session_state, edit_notice_scope], outputs=[edit_selected_to, edit_selected_cc])

        project_dd.change(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        product_line.change(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        reload_btn.click(_list_releases, inputs=[session_state, project_dd, product_line], outputs=[release_table])
        refresh_index_btn.click(_refresh_index, inputs=[session_state, project_dd, product_line], outputs=[publish_status, release_table])
        publish_btn.click(
            _publish,
            inputs=[session_state, project_dd, version_name, release_date, commit, product_line, changelog, files, new_replace_attachments, notice_enabled, notice_scope, selected_to, selected_cc, new_edit_title],
            outputs=[publish_status, release_table],
        )
        edit_project_dd.change(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_filter_product_line.change(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_reload_btn.click(_list_releases, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_table]).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        edit_refresh_index_btn.click(_refresh_index, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_publish_status, edit_release_table])
        edit_release_dd.change(_load_release_to_form, inputs=[session_state, edit_project_dd, edit_release_dd], outputs=[edit_version_name, edit_release_date, edit_commit, edit_product_line, edit_changelog, existing_files_info, edit_replace_attachments])
        edit_publish_btn.click(
            _publish,
            inputs=[session_state, edit_project_dd, edit_version_name, edit_release_date, edit_commit, edit_product_line, edit_changelog, edit_files, edit_replace_attachments, edit_notice_enabled, edit_notice_scope, edit_selected_to, edit_selected_cc, edit_release_dd, edit_filter_product_line],
            outputs=[edit_publish_status, edit_release_table],
        ).then(_release_choices, inputs=[session_state, edit_project_dd, edit_filter_product_line], outputs=[edit_release_dd])
        app.load(
            _restore_connection,
            inputs=[session_state],
            outputs=[connect_status, session_state, login_panel, main_panel, project_dd, config_project_dd, edit_project_dd, release_table, edit_release_table, edit_release_dd],
        ).then(
            _load_notice_settings,
            inputs=[session_state, notice_scope, edit_notice_scope],
            outputs=notice_setting_outputs,
        )
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
