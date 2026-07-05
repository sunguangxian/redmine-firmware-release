"""邮件联系人与发送配置策略。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_external_email_settings,
    get_user_internal_email_settings,
)
from .email_sender import EmailSendError, EmailSettings


def _merge_contact_lists(*groups: List[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            email = (item or "").strip()
            key = email.lower()
            if not email or key in seen:
                continue
            seen.add(key)
            result.append(email)
    return result


def contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    """返回当前用户可选联系人，保留 To/CC 语义。"""
    if scope == MAIL_SCOPE_INTERNAL:
        global_contacts = get_internal_contact_settings()
        user_contacts = get_user_internal_email_settings(session.get("user_key", ""))
        return {
            "contacts_to": _merge_contact_lists(
                global_contacts.get("contacts_to", []),
                user_contacts.get("contacts_to", []),
            ),
            "contacts_cc": _merge_contact_lists(
                global_contacts.get("contacts_cc", []),
                user_contacts.get("contacts_cc", []),
            ),
            "contact_templates": user_contacts.get("contact_templates", []),
        }

    contacts = get_user_external_email_settings(session.get("user_key", ""))
    return {
        "contacts_to": contacts.get("contacts_to", []),
        "contacts_cc": contacts.get("contacts_cc", []),
        "contact_templates": contacts.get("contact_templates", []),
    }


def build_email_settings(session: Dict[str, Any], scope: str) -> Tuple[EmailSettings, List[str], List[str]]:
    """构建邮件发送配置，并返回该 scope 下允许选择的 To/CC 联系人。"""
    if scope == MAIL_SCOPE_INTERNAL:
        server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        user_cfg = get_user_internal_email_settings(session.get("user_key", ""))
        if not user_cfg["smtp_user"] or not user_cfg["smtp_password"]:
            raise EmailSendError("内网邮件请先配置个人 SMTP 用户名和密码")
        if not user_cfg["smtp_from"] and not server["smtp_from"]:
            raise EmailSendError("内网邮件请先配置个人发件人或管理员默认发件人")
        global_contacts = get_internal_contact_settings()
        return (
            EmailSettings(
                smtp_host=server["smtp_host"],
                smtp_port=server["smtp_port"],
                smtp_user=user_cfg["smtp_user"],
                smtp_password=user_cfg["smtp_password"],
                smtp_from=user_cfg["smtp_from"] or server["smtp_from"],
                use_tls=server["use_tls"],
            ),
            _merge_contact_lists(global_contacts.get("contacts_to", []), user_cfg.get("contacts_to", [])),
            _merge_contact_lists(global_contacts.get("contacts_cc", []), user_cfg.get("contacts_cc", [])),
        )

    server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
    user_cfg = get_user_external_email_settings(session.get("user_key", ""))
    if not user_cfg["smtp_user"] or not user_cfg["smtp_password"]:
        raise EmailSendError("外网邮件请先配置个人 SMTP 用户名和密码")
    return (
        EmailSettings(
            smtp_host=server["smtp_host"],
            smtp_port=server["smtp_port"],
            smtp_user=user_cfg["smtp_user"],
            smtp_password=user_cfg["smtp_password"],
            smtp_from=user_cfg["smtp_from"],
            use_tls=server["use_tls"],
        ),
        user_cfg.get("contacts_to", []),
        user_cfg.get("contacts_cc", []),
    )
