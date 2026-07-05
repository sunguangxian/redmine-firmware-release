"""邮件设置保存接口补强。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, FastAPI

from .api_app import AdminMailSettingsRequest, MAIL_SCOPE_EXTERNAL, MAIL_SCOPE_INTERNAL, _current_session, _require_admin
from .config_store import store_email_server_settings, store_internal_contact_settings


def _remove_admin_mail_settings_route(app: FastAPI) -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", "") == "/api/mail/admin-settings"
            and "PUT" in getattr(route, "methods", set())
        )
    ]


def register_mail_settings_routes(app: FastAPI) -> None:
    if getattr(app.state, "mail_settings_routes_registered", False):
        return
    app.state.mail_settings_routes_registered = True
    _remove_admin_mail_settings_route(app)

    @app.put("/api/mail/admin-settings")
    def api_save_admin_mail_settings(
        payload: AdminMailSettingsRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, bool]:
        _require_admin(session)
        store_email_server_settings(
            MAIL_SCOPE_INTERNAL,
            smtp_host=payload.internal_server.smtp_host,
            smtp_port=payload.internal_server.smtp_port,
            smtp_from=payload.internal_server.smtp_from,
            use_tls=payload.internal_server.use_tls,
        )
        store_email_server_settings(
            MAIL_SCOPE_EXTERNAL,
            smtp_host=payload.external_server.smtp_host,
            smtp_port=payload.external_server.smtp_port,
            smtp_from="",
            use_tls=payload.external_server.use_tls,
        )

        contacts_to = payload.internal_contacts.contacts_to or payload.internal_contacts.contacts
        contacts_cc = payload.internal_contacts.contacts_cc
        store_internal_contact_settings(contacts_to=contacts_to, contacts_cc=contacts_cc)
        return {"ok": True}
