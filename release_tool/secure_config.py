"""对现有配置存储增加 SMTP 密码加密兼容层。"""

from __future__ import annotations

from typing import Any

from . import config_store
from .secret_store import protect_secret, unprotect_secret

_PATCHED = False
_ORIGINALS: dict[str, Any] = {}


def _decrypt_email_settings(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data or {})
    result["smtp_password"] = unprotect_secret(str(result.get("smtp_password") or ""))
    return result


def apply_secure_config_patches() -> None:
    """让后续读取/保存 SMTP 密码时自动解密/加密。

    兼容已有明文密码：读取时如果不是加密前缀，会原样返回；下一次保存后会转为加密值。
    """
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    _ORIGINALS["get_user_internal_email_settings"] = config_store.get_user_internal_email_settings
    _ORIGINALS["get_user_external_email_settings"] = config_store.get_user_external_email_settings
    _ORIGINALS["store_user_internal_email_settings"] = config_store.store_user_internal_email_settings
    _ORIGINALS["store_user_external_email_settings"] = config_store.store_user_external_email_settings

    def get_user_internal_email_settings(user_key: str) -> dict[str, Any]:
        return _decrypt_email_settings(_ORIGINALS["get_user_internal_email_settings"](user_key))

    def get_user_external_email_settings(user_key: str) -> dict[str, Any]:
        return _decrypt_email_settings(_ORIGINALS["get_user_external_email_settings"](user_key))

    def store_user_internal_email_settings(user_key: str, **kwargs: Any) -> None:
        if "smtp_password" in kwargs:
            kwargs["smtp_password"] = protect_secret(str(kwargs.get("smtp_password") or ""))
        _ORIGINALS["store_user_internal_email_settings"](user_key, **kwargs)

    def store_user_external_email_settings(user_key: str, **kwargs: Any) -> None:
        if "smtp_password" in kwargs:
            kwargs["smtp_password"] = protect_secret(str(kwargs.get("smtp_password") or ""))
        _ORIGINALS["store_user_external_email_settings"](user_key, **kwargs)

    config_store.get_user_internal_email_settings = get_user_internal_email_settings
    config_store.get_user_external_email_settings = get_user_external_email_settings
    config_store.store_user_internal_email_settings = store_user_internal_email_settings
    config_store.store_user_external_email_settings = store_user_external_email_settings

    # api_app 在 import 时已把函数名导入到模块全局，这里同步替换。
    try:
        from . import api_app

        api_app.get_user_internal_email_settings = get_user_internal_email_settings
        api_app.get_user_external_email_settings = get_user_external_email_settings
        api_app.store_user_internal_email_settings = store_user_internal_email_settings
        api_app.store_user_external_email_settings = store_user_external_email_settings
    except Exception:
        pass
