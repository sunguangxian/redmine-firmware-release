"""邮件设置接口。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, FastAPI, Query

from .api_app import (
    AdminMailSettingsRequest,
    MAIL_SCOPE_EXTERNAL,
    MAIL_SCOPE_INTERNAL,
    UserExternalMailRequest,
    UserInternalMailRequest,
    _contacts_for_scope,
    _current_session,
    _normalize_mail_scope,
    _require_admin,
)
from .audit_log import record_audit
from .config_store import (
    get_email_server_settings,
    get_internal_contact_settings,
    get_user_external_email_settings,
    get_user_internal_email_settings,
    store_email_server_settings,
    store_internal_contact_settings,
    store_user_external_email_settings,
    store_user_internal_email_settings,
)


def _route_has_method(route: Any, method: str) -> bool:
    return method.upper() in set(getattr(route, "methods", set()) or set())


def _remove_existing_mail_settings_routes(app: FastAPI) -> None:
    specs = [
        ("/api/mail/settings", "GET"),
        ("/api/mail/admin-settings", "PUT"),
        ("/api/mail/user-internal-settings", "PUT"),
        ("/api/mail/user-external-settings", "PUT"),
        ("/api/mail/contacts", "GET"),
    ]

    def should_remove(route: Any) -> bool:
        path = getattr(route, "path", "")
        return any(path == target and _route_has_method(route, method) for target, method in specs)

    app.router.routes[:] = [route for route in app.router.routes if not should_remove(route)]


def register_mail_settings_routes(app: FastAPI) -> None:
    if getattr(app.state, "mail_settings_routes_registered", False):
        return
    app.state.mail_settings_routes_registered = True
    _remove_existing_mail_settings_routes(app)

    @app.get("/api/mail/settings")
    def api_mail_settings(session: Dict[str, Any] = Depends(_current_session)) -> Dict[str, Any]:
        internal_server = get_email_server_settings(MAIL_SCOPE_INTERNAL)
        external_server = get_email_server_settings(MAIL_SCOPE_EXTERNAL)
        internal_contacts = get_internal_contact_settings()
        user_internal = get_user_internal_email_settings(session.get("user_key", ""))
        user_external = get_user_external_email_settings(session.get("user_key", ""))
        return {
            "is_admin": bool(session.get("is_admin")),
            "admin": {
                "internal_server": internal_server,
                "external_server": external_server,
                "internal_contacts": internal_contacts,
            },
            "user_internal": {
                "smtp_user": user_internal["smtp_user"],
                "smtp_password": "",
                "smtp_password_set": bool(user_internal.get("smtp_password")),
                "smtp_from": user_internal["smtp_from"],
                "contacts_to": user_internal["contacts_to"],
                "contacts_cc": user_internal["contacts_cc"],
                "contact_templates": user_internal["contact_templates"],
            },
            "user_external": {
                "smtp_user": user_external["smtp_user"],
                "smtp_password": "",
                "smtp_password_set": bool(user_external.get("smtp_password")),
                "smtp_from": user_external["smtp_from"],
                "contacts_to": user_external["contacts_to"],
                "contacts_cc": user_external["contacts_cc"],
                "contact_templates": user_external["contact_templates"],
            },
        }

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
        record_audit(
            actor=session.get("user_login", ""),
            action="mail_admin_settings_updated",
            target_type="mail_settings",
            details={
                "internal_server_configured": bool(payload.internal_server.smtp_host),
                "external_server_configured": bool(payload.external_server.smtp_host),
                "internal_contacts_to_count": len(contacts_to),
                "internal_contacts_cc_count": len(contacts_cc),
            },
        )
        return {"ok": True}

    @app.put("/api/mail/user-internal-settings")
    def api_save_user_internal_mail_settings(
        payload: UserInternalMailRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, bool]:
        user_key = session.get("user_key", "")
        old = get_user_internal_email_settings(user_key)
        smtp_password = payload.smtp_password or old.get("smtp_password", "")
        store_user_internal_email_settings(
            user_key,
            smtp_user=payload.smtp_user,
            smtp_password=smtp_password,
            smtp_from=payload.smtp_from,
            contacts_to=payload.contacts_to,
            contacts_cc=payload.contacts_cc,
            contact_templates=[item.dict() for item in payload.contact_templates],
        )
        return {"ok": True}

    @app.put("/api/mail/user-external-settings")
    def api_save_user_external_mail_settings(
        payload: UserExternalMailRequest,
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, bool]:
        user_key = session.get("user_key", "")
        old = get_user_external_email_settings(user_key)
        smtp_password = payload.smtp_password or old.get("smtp_password", "")
        store_user_external_email_settings(
            user_key,
            smtp_user=payload.smtp_user,
            smtp_password=smtp_password,
            smtp_from=payload.smtp_from,
            contacts_to=payload.contacts_to,
            contacts_cc=payload.contacts_cc,
            contact_templates=[item.dict() for item in payload.contact_templates],
        )
        return {"ok": True}

    @app.get("/api/mail/contacts")
    def api_mail_contacts(
        scope: str = Query(MAIL_SCOPE_INTERNAL),
        session: Dict[str, Any] = Depends(_current_session),
    ) -> Dict[str, Any]:
        return _contacts_for_scope(session, _normalize_mail_scope(scope))
