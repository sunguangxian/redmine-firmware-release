"""邮件范围和联系人 helper。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_internal_contact_settings,
    get_user_internal_email_settings,
)
from .dependencies import _json_error
from .external_account_contacts import get_user_external_email_account_settings

MAIL_SCOPES = {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL}


def normalize_mail_scope(scope: Optional[str]) -> str:
    value = (scope or MAIL_SCOPE_INTERNAL).strip().lower()
    if value not in MAIL_SCOPES:
        raise _json_error("邮件类型只能是 internal 或 external")
    return value


def mail_scope_label(scope: str) -> str:
    return "外网" if scope == MAIL_SCOPE_EXTERNAL else "内网"


def contact_people(emails: List[str]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for email in emails:
        value = (email or "").strip()
        if not value or "@" not in value:
            continue
        result.append({"name": value.split("@")[0] or value, "email": value})
    return result


def merge_contact_lists(*groups: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for group in groups:
        for item in group:
            email = (item or "").strip()
            key = email.lower()
            if not email or key in seen:
                continue
            seen.add(key)
            result.append(email)
    return result


def contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    if scope == MAIL_SCOPE_INTERNAL:
        global_contacts = get_internal_contact_settings()
        user_contacts = get_user_internal_email_settings(session.get("user_key", ""))
        contacts_to = merge_contact_lists(
            global_contacts.get("contacts_to", []),
            user_contacts.get("contacts_to", []),
        )
        contacts_cc = merge_contact_lists(
            global_contacts.get("contacts_cc", []),
            user_contacts.get("contacts_cc", []),
        )
        if not contacts_cc:
            # 兼容旧配置：管理员只维护了一份“内网联系人”时，发布页抄送下拉也应可选这些联系人。
            contacts_cc = list(contacts_to)
        return {
            "contacts_to": contacts_to,
            "contacts_cc": contacts_cc,
            "contact_templates": user_contacts.get("contact_templates", []),
        }

    contacts = get_user_external_email_account_settings(session.get("user_key", ""))
    return {
        "contacts_to": contacts.get("contacts_to", []),
        "contacts_cc": contacts.get("contacts_cc", []),
        "contact_templates": contacts.get("contact_templates", []),
    }
