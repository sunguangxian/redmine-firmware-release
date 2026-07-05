"""本地敏感信息保护。

Windows 生产部署时使用当前机器/当前服务账号的 DPAPI 加密。
非 Windows 环境仅做兼容编码，方便开发机运行；生产环境建议部署在 Windows 并限制数据库文件权限。
"""

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

DPAPI_PREFIX = "dpapi:"
PLAIN64_PREFIX = "plain64:"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob._buffer = buf  # type: ignore[attr-defined]
    return blob


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _protect_dpapi(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return _bytes_from_blob(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect_dpapi(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return _bytes_from_blob(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def protect_secret(value: str) -> str:
    text = value or ""
    if not text:
        return ""
    if text.startswith(DPAPI_PREFIX) or text.startswith(PLAIN64_PREFIX):
        return text
    raw = text.encode("utf-8")
    if os.name == "nt":
        protected = _protect_dpapi(raw)
        return DPAPI_PREFIX + base64.b64encode(protected).decode("ascii")
    return PLAIN64_PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect_secret(value: str) -> str:
    text = value or ""
    if not text:
        return ""
    try:
        if text.startswith(DPAPI_PREFIX):
            raw = base64.b64decode(text[len(DPAPI_PREFIX):])
            return _unprotect_dpapi(raw).decode("utf-8")
        if text.startswith(PLAIN64_PREFIX):
            raw = base64.b64decode(text[len(PLAIN64_PREFIX):])
            return raw.decode("utf-8")
    except Exception:
        return ""
    return text
