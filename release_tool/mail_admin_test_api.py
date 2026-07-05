"""管理员 SMTP 服务器连通性测试接口。"""

from __future__ import annotations

import smtplib
import ssl
from typing import Any, Dict

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .dependencies import _current_session, _json_error, _require_admin
from .email_sender import EmailSendError
from .mail_contact_helpers import mail_scope_label, normalize_mail_scope


class AdminMailServerTestRequest(BaseModel):
    scope: str = "internal"
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_from: str = ""
    use_tls: bool = False


def _test_server_only(payload: AdminMailServerTestRequest) -> None:
    host = (payload.smtp_host or "").strip()
    if not host:
        raise EmailSendError("请先填写 SMTP 服务器")
    port = int(payload.smtp_port or 25)
    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
                smtp.noop()
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if payload.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.noop()
    except Exception as exc:
        raise EmailSendError(f"SMTP 服务器连通性测试失败：{exc}") from exc


def register_admin_mail_test_routes(app: FastAPI) -> None:
    if getattr(app.state, "admin_mail_test_routes_registered", False):
        return
    app.state.admin_mail_test_routes_registered = True

    @app.post("/api/mail/admin-test-connection")
    def api_test_admin_mail_server(
        payload: AdminMailServerTestRequest,
        session: Dict = Depends(_current_session),
    ) -> Dict[str, Any]:
        _require_admin(session)
        scope = normalize_mail_scope(payload.scope)
        try:
            _test_server_only(payload)
        except EmailSendError as exc:
            raise _json_error(str(exc)) from exc
        return {"ok": True, "message": f"{mail_scope_label(scope)} SMTP 服务器连通性测试通过"}
