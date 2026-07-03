"""邮件发送工具。"""

from __future__ import annotations

import mimetypes
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable
from urllib.parse import quote

MAIL_SCOPE_INTERNAL = "internal"
MAIL_SCOPE_EXTERNAL = "external"


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
    template_scope: str = ""


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


def _normalize_mail_scope(mail_scope: str | None) -> str:
    return mail_scope if mail_scope in {MAIL_SCOPE_INTERNAL, MAIL_SCOPE_EXTERNAL} else MAIL_SCOPE_INTERNAL


def build_release_email_subject(project_id: str, version_name: str, product_line: str, mail_scope: str = MAIL_SCOPE_INTERNAL) -> str:
    """构建发布邮件标题。mail_scope 支持 internal/external 两个模板。"""
    scope = _normalize_mail_scope(mail_scope)
    if scope == MAIL_SCOPE_EXTERNAL:
        return build_external_release_email_subject(project_id, version_name, product_line)
    return build_internal_release_email_subject(project_id, version_name, product_line)


def build_internal_release_email_subject(project_id: str, version_name: str, product_line: str) -> str:
    return f"[{project_id}] 固件版本发布 {version_name} - {product_line}"


def build_external_release_email_subject(project_id: str, version_name: str, product_line: str) -> str:
    return f"[Firmware Release][{project_id}] {version_name} - {product_line}"


def build_release_email_body(
    *,
    base_url: str,
    project_id: str,
    wiki_title: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog_items: Iterable[str],
    attachment_names: Iterable[str],
    mail_scope: str = MAIL_SCOPE_INTERNAL,
) -> str:
    """构建发布邮件正文。mail_scope 支持 internal/external 两个模板。"""
    scope = _normalize_mail_scope(mail_scope)
    if scope == MAIL_SCOPE_EXTERNAL:
        return build_external_release_email_body(
            project_id=project_id,
            version_name=version_name,
            release_date=release_date,
            product_line=product_line,
            changelog_items=changelog_items,
            attachment_names=attachment_names,
        )
    return build_internal_release_email_body(
        base_url=base_url,
        project_id=project_id,
        wiki_title=wiki_title,
        version_name=version_name,
        release_date=release_date,
        commit=commit,
        product_line=product_line,
        changelog_items=changelog_items,
        attachment_names=attachment_names,
    )


def build_internal_release_email_body(
    *,
    base_url: str,
    project_id: str,
    wiki_title: str,
    version_name: str,
    release_date: str,
    commit: str,
    product_line: str,
    changelog_items: Iterable[str],
    attachment_names: Iterable[str],
) -> str:
    base = base_url.rstrip("/")
    wiki_url = f"{base}/projects/{quote(project_id)}/wiki/{quote(wiki_title, safe='')}"
    files_url = f"{base}/projects/{quote(project_id)}/files"
    changelog = "\n".join(f"{idx}. {item}" for idx, item in enumerate(changelog_items, 1)) or "（无）"
    attachments = "\n".join(f"- {name}" for name in attachment_names) or "（本次邮件未附加文件，请查看 Redmine 项目文件）"

    return (
        f"固件版本已发布。\n\n"
        f"项目：{project_id}\n"
        f"版本：{version_name}\n"
        f"产品线：{product_line}\n"
        f"发布日期：{release_date}\n"
        f"Commit：{commit}\n\n"
        f"变更说明：\n{changelog}\n\n"
        f"附件：\n{attachments}\n\n"
        f"Wiki：{wiki_url}\n"
        f"项目文件：{files_url}\n"
    )


def build_external_release_email_body(
    *,
    project_id: str,
    version_name: str,
    release_date: str,
    product_line: str,
    changelog_items: Iterable[str],
    attachment_names: Iterable[str],
) -> str:
    changelog = "\n".join(f"{idx}. {item}" for idx, item in enumerate(changelog_items, 1)) or "（无）"
    attachments = "\n".join(f"- {name}" for name in attachment_names) or "（本次邮件未附加文件，请联系相关人员获取固件文件）"

    return (
        f"您好，\n\n"
        f"固件版本已发布，请查收。\n\n"
        f"项目：{project_id}\n"
        f"版本：{version_name}\n"
        f"产品线：{product_line}\n"
        f"发布日期：{release_date}\n\n"
        f"变更说明：\n{changelog}\n\n"
        f"附件：\n{attachments}\n\n"
        f"如有问题，请联系技术支持人员。\n"
    )


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

    subject, body = _apply_template_scope(settings, subject, body)

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


def _apply_template_scope(settings: EmailSettings, subject: str, body: str) -> tuple[str, str]:
    scope = settings.template_scope or (MAIL_SCOPE_EXTERNAL if settings.smtp_user else MAIL_SCOPE_INTERNAL)
    if _normalize_mail_scope(scope) == MAIL_SCOPE_EXTERNAL:
        return _externalize_subject(subject), _externalize_body(body)
    return subject, body


def _externalize_subject(subject: str) -> str:
    if "Firmware Release" in subject:
        return subject
    return subject.replace("固件版本发布", "Firmware Release")


def _externalize_body(body: str) -> str:
    if body.startswith("您好，"):
        return body

    lines = body.splitlines()
    filtered: list[str] = []
    skip_prefixes = ("Commit：", "Wiki：", "项目文件：")
    for line in lines:
        if line.startswith(skip_prefixes):
            continue
        filtered.append(line)

    while filtered and not filtered[0].strip():
        filtered.pop(0)
    if filtered and filtered[0].strip() == "固件版本已发布。":
        filtered.pop(0)

    return "\n".join([
        "您好，",
        "",
        "固件版本已发布，请查收。",
        "",
        *filtered,
        "",
        "如有问题，请联系技术支持人员。",
    ]).strip() + "\n"


def _smtp_login_if_needed(smtp: smtplib.SMTP, settings: EmailSettings) -> None:
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password or "")
