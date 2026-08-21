"""邮件范围和联系人 helper。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config_store import (
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    get_internal_contact_settings,
    get_user_internal_email_settings,
    store_user_internal_email_settings,
)
from .dependencies import _json_error
from .external_account_contacts import (
    get_user_external_email_account_settings,
    store_user_external_email_account_settings,
)
from .internal_contact_people import clean_people, get_internal_contact_people

MAIL_SCOPES = {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL}


def normalize_mail_scope(scope: Optional[str]) -> str:
    value = (scope or MAIL_SCOPE_INTERNAL).strip().lower()
    if value not in MAIL_SCOPES:
        raise _json_error("邮件类型只能是 internal 或 external")
    return value


def mail_scope_label(scope: str) -> str:
    return "外网" if scope == MAIL_SCOPE_EXTERNAL else "内网"


def contact_people(emails: List[str]) -> List[Dict[str, str]]:
    return clean_people(None, emails)


def _people_for_emails(people: list[dict[str, str]], emails: list[str]) -> list[dict[str, str]]:
    by_email = {item["email"].strip().lower(): item for item in clean_people(people)}
    result: list[dict[str, str]] = []
    for email in emails:
        key = email.strip().lower()
        result.append(by_email.get(key) or {"name": email.split("@")[0], "email": email})
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


def save_new_contacts_for_scope(
    session: Dict[str, Any],
    scope: str,
    contacts_to: List[str],
    contacts_cc: List[str],
) -> None:
    """将成功使用的新收件人合并到当前邮件账户的联系人列表。"""
    user_key = session.get("user_key", "")
    if not user_key:
        return

    if scope == MAIL_SCOPE_INTERNAL:
        settings = get_user_internal_email_settings(user_key)
        global_contacts = get_internal_contact_settings()
        known_to = merge_contact_lists(global_contacts.get("contacts_to", []), settings.get("contacts_to", []))
        known_cc = merge_contact_lists(global_contacts.get("contacts_cc", []), settings.get("contacts_cc", []))
        new_to = [item for item in merge_contact_lists(contacts_to) if item.lower() not in {email.lower() for email in known_to}]
        new_cc = [item for item in merge_contact_lists(contacts_cc) if item.lower() not in {email.lower() for email in known_cc}]
        if not new_to and not new_cc:
            return
        store_user_internal_email_settings(
            user_key,
            smtp_user=settings.get("smtp_user", ""),
            smtp_password=settings.get("smtp_password", ""),
            smtp_from=settings.get("smtp_from", ""),
            contacts_to=merge_contact_lists(settings.get("contacts_to", []), new_to),
            contacts_cc=merge_contact_lists(settings.get("contacts_cc", []), new_cc),
            contact_templates=settings.get("contact_templates", []),
        )
        return

    settings = get_user_external_email_account_settings(user_key)
    new_to = [item for item in merge_contact_lists(contacts_to) if item.lower() not in {email.lower() for email in settings.get("contacts_to", [])}]
    new_cc = [item for item in merge_contact_lists(contacts_cc) if item.lower() not in {email.lower() for email in settings.get("contacts_cc", [])}]
    if not new_to and not new_cc:
        return
    store_user_external_email_account_settings(
        user_key,
        smtp_user=settings.get("smtp_user", ""),
        smtp_password=settings.get("smtp_password", ""),
        smtp_from=settings.get("smtp_from", ""),
        contacts_to=merge_contact_lists(settings.get("contacts_to", []), new_to),
        contacts_cc=merge_contact_lists(settings.get("contacts_cc", []), new_cc),
        contacts_to_people=merge_people(settings.get("contacts_to_people", []), contact_people(new_to)),
        contacts_cc_people=merge_people(settings.get("contacts_cc_people", []), contact_people(new_cc)),
        contact_templates=settings.get("contact_templates", []),
    )


def merge_people(*groups: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            email = str((item or {}).get("email") or "").strip()
            key = email.lower()
            if not email or key in seen:
                continue
            seen.add(key)
            result.append({"name": str((item or {}).get("name") or "").strip() or email.split("@")[0], "email": email})
    return result


def contacts_for_scope(session: Dict[str, Any], scope: str) -> Dict[str, Any]:
    if scope == MAIL_SCOPE_INTERNAL:
        global_contacts = get_internal_contact_settings()
        named_global_people = get_internal_contact_people() or contact_people(global_contacts.get("contacts_to", []))
        user_contacts = get_user_internal_email_settings(session.get("user_key", ""))
        contacts_to = merge_contact_lists(global_contacts.get("contacts_to", []), user_contacts.get("contacts_to", []))
        contacts_cc = merge_contact_lists(global_contacts.get("contacts_cc", []), user_contacts.get("contacts_cc", []))
        if not contacts_cc:
            contacts_cc = list(contacts_to)
        contacts_to_people = _people_for_emails(named_global_people + contact_people(user_contacts.get("contacts_to", [])), contacts_to)
        contacts_cc_people = _people_for_emails(named_global_people + contact_people(user_contacts.get("contacts_cc", [])), contacts_cc)
        return {
            "contacts_to": contacts_to,
            "contacts_cc": contacts_cc,
            "contacts_to_people": contacts_to_people,
            "contacts_cc_people": contacts_cc_people,
            "contact_templates": user_contacts.get("contact_templates", []),
        }

    contacts = get_user_external_email_account_settings(session.get("user_key", ""))
    contacts_to = contacts.get("contacts_to", [])
    contacts_cc = contacts.get("contacts_cc", [])
    contacts_to_people = contacts.get("contacts_to_people") or contact_people(contacts_to)
    contacts_cc_people = contacts.get("contacts_cc_people") or contact_people(contacts_cc)
    if not contacts_cc:
        contacts_cc = list(contacts_to)
        contacts_cc_people = list(contacts_to_people)
    return {
        "contacts_to": contacts_to,
        "contacts_cc": contacts_cc,
        "contacts_to_people": contacts_to_people,
        "contacts_cc_people": contacts_cc_people,
        "contact_templates": contacts.get("contact_templates", []),
    }
