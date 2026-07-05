"""邮件通知字段校验 helper。"""

from __future__ import annotations

from typing import List, Tuple

from fastapi import HTTPException

from .email_sender import EmailSendError, split_emails
from .mail_contact_helpers import normalize_mail_scope


def validate_notice_fields(
    mail_scope: str,
    mail_to: str,
    mail_cc: str,
    mail_subject: str,
    mail_body: str,
) -> Tuple[str, List[str], List[str]]:
    try:
        scope = normalize_mail_scope(mail_scope)
    except HTTPException as exc:
        raise EmailSendError(str(exc.detail)) from exc

    to_addrs = split_emails(mail_to)
    cc_addrs = split_emails(mail_cc)
    if not to_addrs:
        raise EmailSendError("请填写或选择至少一个收件人")
    if not (mail_subject or "").strip():
        raise EmailSendError("请先生成或填写邮件主题")
    if not (mail_body or "").strip():
        raise EmailSendError("请先生成或填写邮件正文")
    return scope, to_addrs, cc_addrs
