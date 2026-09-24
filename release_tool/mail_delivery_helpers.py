"""邮件配置构造、通知预检查和发送 helper。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlparse

from .attachment_policy import MAX_MAIL_ATTACHMENT_BYTES, AttachmentContent
from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_internal_email_settings,
)
from .email_sender import EmailSendError, EmailSettings, send_release_email, split_emails
from .external_account_contacts import get_user_external_email_account_settings
from .mail_contact_helpers import mail_scope_label, merge_contact_lists, save_new_contacts_for_scope
from .mail_history import record_mail_send
from .mail_notice_helpers import validate_notice_fields
from .redmine_api import RedmineClient, RedmineError
from .release_page import extract_inline_release_block, parse_inline_ref, parse_release_files

_CREDENTIAL_FIELD = "smtp_" + "password"
_USER_FIELD = "smtp_user"
_FROM_FIELD = "smtp_from"


def _setting_value(values: Dict[str, Any], key: str, default: Any = "") -> Any:
    return values.get(key, default)


def _email_settings(
    *,
    server: Dict[str, Any],
    user_cfg: Dict[str, Any],
    sender: str,
) -> EmailSettings:
    return EmailSettings(
        smtp_host=server["smtp_host"],
        smtp_port=server["smtp_port"],
        smtp_user=_setting_value(user_cfg, _USER_FIELD),
        smtp_password=_setting_value(user_cfg, _CREDENTIAL_FIELD),
        smtp_from=sender,
        use_tls=server["use_tls"],
    )


def build_email_settings(session: Dict[str, Any], scope: str) -> Tuple[EmailSettings, List[str], List[str]]:
    if scope == MAIL_SCOPE_INTERNAL:
        server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        user_cfg = get_user_internal_email_settings(session.get("user_key", ""))
        if not user_cfg[_USER_FIELD] or not user_cfg[_CREDENTIAL_FIELD]:
            raise EmailSendError("内网邮件请先配置个人 SMTP 用户名和密码")
        if not user_cfg[_FROM_FIELD] and not server[_FROM_FIELD]:
            raise EmailSendError("内网邮件请先配置个人发件人或管理员默认发件人")
        global_contacts = get_internal_contact_settings()
        return (
            _email_settings(
                server=server,
                user_cfg=user_cfg,
                sender=user_cfg[_FROM_FIELD] or server[_FROM_FIELD],
            ),
            merge_contact_lists(global_contacts.get("contacts_to", []), user_cfg.get("contacts_to", [])),
            merge_contact_lists(global_contacts.get("contacts_cc", []), user_cfg.get("contacts_cc", [])),
        )

    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    user_cfg = get_user_external_email_account_settings(session.get("user_key", ""))
    if not user_cfg[_USER_FIELD] or not user_cfg[_CREDENTIAL_FIELD]:
        raise EmailSendError("外网邮件请先配置个人 SMTP 用户名和密码")
    return (
        _email_settings(
            server=server,
            user_cfg=user_cfg,
            sender=user_cfg[_FROM_FIELD],
        ),
        user_cfg["contacts_to"],
        user_cfg["contacts_cc"],
    )


def validate_notice_preflight(
    session: Dict[str, Any],
    mail_scope: str,
    mail_to: str,
    mail_cc: str,
    mail_subject: str,
    mail_body: str,
) -> Tuple[str, List[str], List[str]]:
    scope, to_addrs, cc_addrs = validate_notice_fields(mail_scope, mail_to, mail_cc, mail_subject, mail_body)
    settings, _allowed_to, _allowed_cc = build_email_settings(session, scope)
    if not settings.smtp_host:
        raise EmailSendError("请先填写 SMTP 服务器")
    if not settings.smtp_from:
        raise EmailSendError("请先填写发件人邮箱")
    return scope, to_addrs, cc_addrs


def _format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _redmine_attachment_path(base_url: str, content_url: str, filename: str) -> str:
    value = (content_url or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlparse(value)
    base = urlparse(base_url or "")
    same_host = parsed.netloc.lower() == (base.netloc or "").lower()
    if parsed.scheme in {"http", "https"} and same_host and parsed.path.startswith("/"):
        if parsed.query:
            return f"{parsed.path}?{parsed.query}"
        return parsed.path
    raise EmailSendError(f"固件附件下载地址不在当前 Redmine：{filename}。未发送邮件。")


def _published_release_text(client: RedmineClient, project_id: str, wiki_title: str) -> str:
    inline = parse_inline_ref(wiki_title)
    try:
        if inline:
            page = client.get_wiki_page(project_id, inline[0])
            if not page:
                raise EmailSendError("未找到已发布版本，无法补发邮件。未发送邮件。")
            block = extract_inline_release_block(page.get("text") or "", inline[1])
            if not block:
                raise EmailSendError("未找到已发布版本，无法补发邮件。未发送邮件。")
            return block
        page = client.get_wiki_page(project_id, wiki_title)
    except EmailSendError:
        raise
    except RedmineError as exc:
        raise EmailSendError(f"读取已发布版本失败：{exc}。未发送邮件。") from exc
    if not page:
        raise EmailSendError("未找到已发布版本，无法补发邮件。未发送邮件。")
    return page.get("text") or ""


def load_published_mail_attachments(
    client: RedmineClient,
    project_id: str,
    wiki_title: str,
) -> List[Tuple[str, str, bytes]]:
    """下载该版本 Wiki 固件表中的全部文件，供补发邮件附件使用。"""
    files = [item for item in parse_release_files(_published_release_text(client, project_id, wiki_title)) if (item.get("filename") or "").strip()]
    if not files:
        raise EmailSendError("该版本没有可随邮件发送的固件附件。未发送邮件。")
    missing = [str(item.get("filename") or "") for item in files if not (item.get("url") or "").strip()]
    if missing:
        raise EmailSendError(f"固件附件缺少下载地址：{'、'.join(missing)}。未发送邮件。")

    rows: List[Tuple[str, str, bytes]] = []
    for item in files:
        filename = str(item.get("filename") or "")
        path = _redmine_attachment_path(client.base_url, str(item.get("url") or ""), filename)
        try:
            content = client.download_content_url(path)
        except RedmineError as exc:
            raise EmailSendError(f"下载固件附件失败：{filename}。{exc}。未发送邮件。") from exc
        if not content:
            raise EmailSendError(f"固件附件为空：{filename}。未发送邮件。")
        rows.append((filename, str(item.get("description") or ""), content))

    total = sum(len(content) for _filename, _description, content in rows)
    if total > MAX_MAIL_ATTACHMENT_BYTES:
        names = "、".join(filename for filename, _description, _content in rows)
        raise EmailSendError(
            f"邮件附件总大小超过限制：{names} 合计 {_format_bytes(total)}，最大 {_format_bytes(MAX_MAIL_ATTACHMENT_BYTES)}。未发送邮件。"
        )
    return rows


def build_notice_body(client: RedmineClient, project_id: str, wiki_title: str, body: str) -> Tuple[str, str]:
    inline = parse_inline_ref(wiki_title)
    normalized_wiki_title = inline[0] if inline else wiki_title
    base = client.base_url.rstrip("/")
    result = (body or "").strip()
    result = result.replace("{{wiki_url}}", f"{base}/projects/{quote(project_id)}/wiki/{quote(normalized_wiki_title, safe='')}")
    result = result.replace("{{files_url}}", f"{base}/projects/{quote(project_id)}/files")
    return normalized_wiki_title, result


def send_release_notice(
    *,
    session: Dict[str, Any],
    client: RedmineClient,
    project_id: str,
    wiki_title: str,
    version_name: str = "",
    file_rows: List[Tuple[str, str, AttachmentContent]],
    mail_scope: str,
    mail_to: List[str],
    mail_cc: List[str],
    mail_subject: str = "",
    mail_body: str = "",
    send_type: str = "publish",
) -> str:
    settings, _allowed_to, _allowed_cc = build_email_settings(session, mail_scope)
    to_addrs = split_emails(mail_to)
    cc_addrs = split_emails(mail_cc)
    subject = (mail_subject or "").strip()
    if not subject or not (mail_body or "").strip():
        raise EmailSendError("请先生成或填写邮件主题和正文")
    normalized_wiki_title, body = build_notice_body(client, project_id, wiki_title, mail_body)
    try:
        send_release_email(
            settings,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=subject,
            body=body,
            attachments=file_rows,
        )
        record_mail_send(
            project_id=project_id,
            wiki_title=normalized_wiki_title,
            version_name=version_name,
            scope=mail_scope,
            subject=subject,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            attachment_count=len(file_rows),
            sender_user=session.get("user_login", ""),
            status="success",
            send_type=send_type,
        )
        save_new_contacts_for_scope(session, mail_scope, to_addrs, cc_addrs)
    except EmailSendError as exc:
        record_mail_send(
            project_id=project_id,
            wiki_title=normalized_wiki_title,
            version_name=version_name,
            scope=mail_scope,
            subject=subject,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            attachment_count=len(file_rows),
            sender_user=session.get("user_login", ""),
            status="failed",
            error_message=str(exc),
            send_type=send_type,
        )
        raise
    return f"{mail_scope_label(mail_scope)}邮件已发送：收件人 {len(to_addrs)} 个，抄送 {len(cc_addrs)} 个，附件 {len(file_rows)} 个"
