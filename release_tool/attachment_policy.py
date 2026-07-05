"""发布附件校验策略。"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable

from .redmine_api import RedmineError

MAX_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_ATTACHMENT_MB", "200")) * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_TOTAL_ATTACHMENT_MB", "800")) * 1024 * 1024


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_attachment(filename: str, content: bytes) -> None:
    name = (filename or "").strip()
    if not name:
        raise RedmineError("附件文件名为空")
    size = len(content or b"")
    if size <= 0:
        raise RedmineError(f"附件为空：{name}")
    if size > MAX_ATTACHMENT_BYTES:
        limit_mb = MAX_ATTACHMENT_BYTES // 1024 // 1024
        raise RedmineError(f"附件过大：{name}，单文件最大 {limit_mb} MB")


def validate_attachment_batch(files: Iterable[tuple[str, str, bytes]]) -> None:
    total = 0
    for filename, _description, content in files:
        validate_attachment(filename, content)
        total += len(content or b"")
    if total > MAX_TOTAL_ATTACHMENT_BYTES:
        limit_mb = MAX_TOTAL_ATTACHMENT_BYTES // 1024 // 1024
        raise RedmineError(f"附件总大小超过限制：最大 {limit_mb} MB")
