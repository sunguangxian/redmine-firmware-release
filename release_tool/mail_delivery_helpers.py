"""邮件配置构造、通知预检查和发送 helper。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_internal_email_settings,
)
from .email_sender import EmailSendError, EmailSettings, send_release_email, split_emails
from .external_account_contacts import get_user_external_email_account_settings
from .mail_contact_helpers import mail_scope_label, merge_contact_lists
from .mail_history import record_mail_send
from .mail_notice_helpers import validate_notice_fields
from .redmine_api import RedmineClient
from .release_page import parse_inline_ref

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
    file_rows: List[Tuple[str, str, bytes]],
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
