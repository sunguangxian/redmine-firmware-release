"""邮件发送工具。"""

from __future__ import annotations

import mimetypes
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

class EmailSendError(Exception):
    pass


@dataclass
class EmailSettings:
    smtp_host: str
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    use_tls: bool = False


_EMAIL_SPLIT_RE = re.compile(r"[;,，；\s]+")


def split_emails(*values: object) -> list[str]:
    """把手动输入和选择项合并为邮箱列表，自动去重。"""
    result: list[str] = []
    seen: set[str] = set()

    def add_one(value: object) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add_one(item)
            return
        for item in _EMAIL_SPLIT_RE.split(str(value).strip()):
            email = item.strip()
            if not email or "@" not in email:
                continue
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(email)

    for value in values:
        add_one(value)
    return result


def normalize_contact_lines(text: str) -> list[str]:
    return split_emails(text or "")


def send_release_email(
    settings: EmailSettings,
    *,
    to_addrs: list[str],
    cc_addrs: list[str] | None,
    subject: str,
    body: str,
    attachments: list[tuple[str, str, bytes]],
) -> None:
    if not settings.smtp_host:
        raise EmailSendError("请先填写 SMTP 服务器")
    if not settings.smtp_from:
        raise EmailSendError("请先填写发件人邮箱")
    if not to_addrs:
        raise EmailSendError("请填写或选择至少一个收件人")

    cc_addrs = cc_addrs or []
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg.set_content(body)

    for filename, _description, content in attachments:
        if not content:
            continue
        mime_type, _encoding = mimetypes.guess_type(filename)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    recipients = to_addrs + cc_addrs
    try:
        if int(settings.smtp_port) == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.smtp_host, int(settings.smtp_port), timeout=60, context=context) as smtp:
                _smtp_login_if_needed(smtp, settings)
                smtp.send_message(msg, from_addr=settings.smtp_from, to_addrs=recipients)
        else:
            with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=60) as smtp:
                smtp.ehlo()
                if settings.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                _smtp_login_if_needed(smtp, settings)
                smtp.send_message(msg, from_addr=settings.smtp_from, to_addrs=recipients)
    except Exception as exc:  # noqa: BLE001 - 展示给用户的桌面工具，需要保留原始错误信息
        raise EmailSendError(str(exc)) from exc


def _smtp_login_if_needed(smtp: smtplib.SMTP, settings: EmailSettings) -> None:
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password or "")
