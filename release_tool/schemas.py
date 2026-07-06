"""FastAPI 请求和响应模型。"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    auth_mode: str = "password"
    username: str = ""
    password: str = ""
    api_key: str = ""
    remember: bool = False


class LoginResponse(BaseModel):
    connected: bool
    user_login: str
    is_admin: bool
    projects: List[Dict[str, Any]]


class SmtpServerConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_from: str = ""
    use_tls: bool = False


class ContactConfig(BaseModel):
    contacts: List[str] = Field(default_factory=list)
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)


class ContactPersonConfig(BaseModel):
    name: str = ""
    email: str = ""


class ContactTemplateConfig(BaseModel):
    name: str = ""
    contacts_to: List[ContactPersonConfig] = Field(default_factory=list)
    contacts_cc: List[ContactPersonConfig] = Field(default_factory=list)


class AdminMailSettingsRequest(BaseModel):
    internal_server: SmtpServerConfig
    external_server: SmtpServerConfig
    internal_contacts: ContactConfig


class UserExternalMailRequest(BaseModel):
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)
    contacts_to_people: List[ContactPersonConfig] = Field(default_factory=list)
    contacts_cc_people: List[ContactPersonConfig] = Field(default_factory=list)
    contact_templates: List[ContactTemplateConfig] = Field(default_factory=list)


class UserInternalMailRequest(BaseModel):
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    contacts_to: List[str] = Field(default_factory=list)
    contacts_cc: List[str] = Field(default_factory=list)
    contact_templates: List[ContactTemplateConfig] = Field(default_factory=list)
