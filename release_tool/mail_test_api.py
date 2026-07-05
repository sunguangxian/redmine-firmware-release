"""邮件账号连通性测试接口。"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from . import config_store
from .config_store import MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL
from .dependencies import _current_session, _json_error
from .email_sender import EmailSendError, EmailSettings, test_smtp_connection
from .mail_contact_helpers import mail_scope_label, normalize_mail_scope


class MailConnectionTestRequest(BaseModel):
    scope: str = MAIL_SCOPE_INTERNAL
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


def _stored_user_mail_settings(scope: str, user_key: str) -> Dict[str, Any]:
    if scope == MAIL_SCOPE_INTERNAL:
        return config_store.get_user_internal_email_settings(user_key)
    if scope == MAIL_SCOPE_EXTERNAL:
        return config_store.get_user_external_email_settings(user_key)
    return {}


def _build_test_settings(payload: MailConnectionTestRequest, session: Dict[str, Any]) -> Tuple[str, EmailSettings]:
    scope = normalize_mail_scope(payload.scope)
    server = config_store.get_email_server_settings(scope)
    user_cfg = _stored_user_mail_settings(scope, session.get("user_key", ""))
    password = payload.smtp_password or user_cfg.get("smtp_password", "")
    sender = payload.smtp_from or user_cfg.get("smtp_from", "") or server.get("smtp_from", "")
    return (
        scope,
        EmailSettings(
            smtp_host=server.get("smtp_host", ""),
            smtp_port=int(server.get("smtp_port") or 25),
            smtp_user=(payload.smtp_user or "").strip(),
            smtp_password=password,
            smtp_from=sender,
            use_tls=bool(server.get("use_tls")),
        ),
    )


def register_mail_test_routes(app: FastAPI) -> None:
    if getattr(app.state, "mail_test_routes_registered", False):
        return
    app.state.mail_test_routes_registered = True

    @app.post("/api/mail/test-connection")
    def api_test_mail_connection(
        payload: MailConnectionTestRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        scope, settings = _build_test_settings(payload, session)
        try:
            test_smtp_connection(settings)
        except EmailSendError as exc:
            raise _json_error(str(exc)) from exc
        return {"ok": True, "message": f"{mail_scope_label(scope)} SMTP 连通性测试通过"}
