"""内联版本模式下的邮件 Wiki 链接兼容。"""

from __future__ import annotations

from typing import Any, Callable

from .release_page import parse_inline_ref

_PATCHED = False
_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _normalize_wiki_title(wiki_title: str) -> str:
    inline = parse_inline_ref(wiki_title)
    return inline[0] if inline else wiki_title


def _wrap_send_notice(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if "wiki_title" in kwargs:
            kwargs["wiki_title"] = _normalize_wiki_title(str(kwargs.get("wiki_title") or ""))
        return func(*args, **kwargs)

    return wrapped


def apply_inline_notice_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from . import api_app, release_ops_api, release_publish_api

    _ORIGINALS["api_app"] = api_app._send_release_notice
    _ORIGINALS["release_ops_api"] = release_ops_api._send_release_notice
    _ORIGINALS["release_publish_api"] = release_publish_api._send_release_notice

    api_app._send_release_notice = _wrap_send_notice(api_app._send_release_notice)
    release_ops_api._send_release_notice = _wrap_send_notice(release_ops_api._send_release_notice)
    release_publish_api._send_release_notice = _wrap_send_notice(release_publish_api._send_release_notice)
