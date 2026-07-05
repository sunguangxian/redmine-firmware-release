"""发布附件校验策略。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

from .redmine_api import RedmineError

DEFAULT_ALLOWED_EXTENSIONS = ".bin,.zip,.hex,.dfu,.img,.tar,.gz,.7z,.rar,.pdf,.txt,.md"
ALLOWED_ATTACHMENT_EXTENSIONS = {
    item.strip().lower()
    for item in os.environ.get("RELEASE_TOOL_ALLOWED_ATTACHMENT_EXTENSIONS", DEFAULT_ALLOWED_EXTENSIONS).split(",")
    if item.strip()
}
MAX_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_ATTACHMENT_MB", "200")) * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = int(os.environ.get("RELEASE_TOOL_MAX_TOTAL_ATTACHMENT_MB", "800")) * 1024 * 1024


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_attachment(filename: str, content: bytes) -> None:
    name = (filename or "").strip()
    if not name:
        raise RedmineError("附件文件名为空")
    suffix = Path(name).suffix.lower()
    if ALLOWED_ATTACHMENT_EXTENSIONS and suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
        allowed = "、".join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))
        raise RedmineError(f"附件类型不允许：{name}，允许类型：{allowed}")
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
