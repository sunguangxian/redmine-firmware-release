"""为发布接口返回 Redmine 和邮件拆分状态。"""

from __future__ import annotations

import json
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _mail_status_from_notice(notice_message: str) -> str:
    if not notice_message:
        return "skipped"
    if notice_message.startswith("邮件发送失败"):
        return "failed"
    return "success"


def _mail_status_label(status: str) -> str:
    if status == "success":
        return "成功"
    if status == "failed":
        return "失败，可重试"
    return "未启用"


def register_release_status_patch(app: FastAPI) -> None:
    if getattr(app.state, "release_status_patch_registered", False):
        return
    app.state.release_status_patch_registered = True

    @app.middleware("http")
    async def release_status_middleware(request: Request, call_next: Callable):
        response = await call_next(request)
        if request.url.path != "/api/releases/publish" or response.status_code != 200:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return JSONResponse(content={"ok": False, "detail": "发布结果解析失败"}, status_code=500)

        mail_status = _mail_status_from_notice(str(data.get("notice_message") or ""))
        data["release_status"] = "success"
        data["release_status_label"] = "Redmine 发布成功"
        data["mail_status"] = mail_status
        data["mail_status_label"] = f"邮件发送{_mail_status_label(mail_status)}"
        data["result_summary"] = f"Redmine 发布：成功\n邮件发送：{_mail_status_label(mail_status)}"
        return JSONResponse(content=data, status_code=response.status_code)
