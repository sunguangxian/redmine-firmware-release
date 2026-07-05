"""把现有邮件发送函数包装为自动记录历史。"""

from __future__ import annotations

from typing import Any, Callable

from .email_sender import EmailSendError, split_emails
from .mail_history import record_mail_send

_APPLIED = False
_ORIGINAL_SEND: Callable[..., str] | None = None


def apply_mail_history_patch() -> None:
    global _APPLIED, _ORIGINAL_SEND
    if _APPLIED:
        return
    _APPLIED = True

    from . import api_app

    _ORIGINAL_SEND = api_app._send_release_notice

    def wrapped_send_release_notice(**kwargs: Any) -> str:
        session = kwargs.get("session") or {}
        project_id = kwargs.get("project_id") or ""
        wiki_title = kwargs.get("wiki_title") or ""
        mail_scope = kwargs.get("mail_scope") or ""
        mail_to = split_emails(kwargs.get("mail_to") or [])
        mail_cc = split_emails(kwargs.get("mail_cc") or [])
        mail_subject = (kwargs.get("mail_subject") or "").strip()
        file_rows = kwargs.get("file_rows") or []
        sender_user = session.get("user_login", "")
        try:
            message = _ORIGINAL_SEND(**kwargs)  # type: ignore[misc]
            record_mail_send(
                project_id=project_id,
                wiki_title=wiki_title,
                scope=mail_scope,
                subject=mail_subject,
                to_addrs=mail_to,
                cc_addrs=mail_cc,
                attachment_count=len(file_rows),
                sender_user=sender_user,
                status="success",
                send_type="publish",
            )
            return message
        except EmailSendError as exc:
            record_mail_send(
                project_id=project_id,
                wiki_title=wiki_title,
                scope=mail_scope,
                subject=mail_subject,
                to_addrs=mail_to,
                cc_addrs=mail_cc,
                attachment_count=len(file_rows),
                sender_user=sender_user,
                status="failed",
                error_message=str(exc),
                send_type="publish",
            )
            raise

    api_app._send_release_notice = wrapped_send_release_notice
