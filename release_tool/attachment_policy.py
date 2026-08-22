"""发布附件校验策略。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO, Iterable, Union

from .redmine_api import RedmineError

MAX_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_ATTACHMENT_MB", "200")) * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_TOTAL_ATTACHMENT_MB", "800")) * 1024 * 1024
MAX_MAIL_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_MAIL_ATTACHMENT_MB", "50")) * 1024 * 1024
AttachmentContent = Union[bytes, BinaryIO, Path]


def content_size(content: AttachmentContent) -> int:
    if isinstance(content, bytes):
        return len(content)
    if isinstance(content, Path):
        return content.stat().st_size
    position = content.tell()
    content.seek(0, os.SEEK_END)
    size = content.tell()
    content.seek(position)
    return int(size)


def content_bytes(content: AttachmentContent) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, Path):
        return content.read_bytes()
    position = content.tell()
    content.seek(0)
    data = content.read()
    content.seek(position)
    return data


def sha256_hex(content: AttachmentContent) -> str:
    if isinstance(content, bytes):
        return hashlib.sha256(content).hexdigest()
    digest = hashlib.sha256()
    if isinstance(content, Path):
        with content.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    position = content.tell()
    content.seek(0)
    for chunk in iter(lambda: content.read(1024 * 1024), b""):
        digest.update(chunk)
    content.seek(position)
    return digest.hexdigest()


def validate_attachment(filename: str, content: AttachmentContent) -> None:
    name = (filename or "").strip()
    if not name:
        raise RedmineError("附件文件名为空")
    size = content_size(content)
    if size <= 0:
        raise RedmineError(f"附件为空：{name}")
    if size > MAX_ATTACHMENT_BYTES:
        limit_mb = MAX_ATTACHMENT_BYTES // 1024 // 1024
        raise RedmineError(f"附件过大：{name}，单文件最大 {limit_mb} MB")


def validate_attachment_batch(files: Iterable[tuple[str, str, AttachmentContent]]) -> None:
    total = 0
    for filename, _description, content in files:
        validate_attachment(filename, content)
        total += content_size(content)
    if total > MAX_TOTAL_ATTACHMENT_BYTES:
        limit_mb = MAX_TOTAL_ATTACHMENT_BYTES // 1024 // 1024
        raise RedmineError(f"附件总大小超过限制：最大 {limit_mb} MB")


def validate_mail_attachment_batch(files: Iterable[tuple[str, str, AttachmentContent]]) -> None:
    total = sum(content_size(content) for _filename, _description, content in files)
    if total > MAX_MAIL_ATTACHMENT_BYTES:
        limit_mb = MAX_MAIL_ATTACHMENT_BYTES // 1024 // 1024
        raise RedmineError(f"邮件附件总大小超过限制：最大 {limit_mb} MB")
