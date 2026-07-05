"""Build a release execution plan shared by preview and publish APIs."""

from __future__ import annotations

from typing import Any

from .publisher import ReleasePublisher
from .redmine_api import RedmineClient
from .release_page import (
    ReleaseForm,
    extract_inline_release_block,
    inline_ref,
    parse_inline_ref,
    parse_release_files,
    parse_release_page,
)
from .release_structure_guard import ensure_release_structure_ready


def _size_text(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


class ReleasePlanner:
    def __init__(self, client: RedmineClient):
        self.client = client

    def build_plan(
        self,
        form: ReleaseForm,
        *,
        new_files: list[dict[str, Any]] | None = None,
        notice_enabled: bool = False,
        mail_scope_label: str = "",
        mail_to_count: int = 0,
        mail_cc_count: int = 0,
        logs: list[str] | None = None,
    ) -> dict[str, Any]:
        index_sync, profile = ensure_release_structure_ready(self.client, form.project_id, logs)
        publisher = ReleasePublisher(self.client)
        publisher._validate_category(form, index_sync, profile, logs)
        mode = getattr(profile, "release_detail_mode", "inline")
        version_name_final = publisher._configured_version_name(form, index_sync, profile)
        version_plan = "将复用已有 Version"
        if not any(v.get("name", "").strip() == version_name_final for v in self.client.list_versions(form.project_id)):
            version_plan = "将创建新 Version"

        warnings: list[str] = []
        old_files: list[dict[str, Any]] = []
        container_page = ""
        block_id = ""
        old_block_id = ""
        is_edit = bool(form.wiki_title)
        old_display_version = ""

        if mode == "inline":
            inline_target = parse_inline_ref(form.wiki_title)
            if inline_target:
                container_page, old_block_id = inline_target
                block_id = old_block_id
                page = self.client.get_wiki_page(form.project_id, container_page)
                block = extract_inline_release_block((page or {}).get("text", ""), block_id)
                old_display_version = self._inline_display_version(block_id, block)
                old_files = parse_release_files(block) if block else []
                target_page = inline_ref(container_page, block_id)
                display_target = f"{container_page} / {form.version_name}"
                new_block_id = publisher._next_block_id(block_id, old_display_version, form.version_name, True)
                if block_id == (old_display_version or block_id) and block_id != form.version_name.strip():
                    warnings.append(f"本次会把旧内联版本块 {block_id} 重命名为 {form.version_name.strip()}。")
                elif block_id != form.version_name.strip():
                    warnings.append(f"本次会保留唯一块标识 {block_id}，页面显示版本更新为 {form.version_name.strip()}。")
                block_id = new_block_id
            else:
                container_page = index_sync.inline_container_for_release(
                    profile,
                    form.page_title,
                    f"**产品线:** {form.product_line}\n**Commit:** {form.commit}\n",
                )
                block_id = form.version_name.strip()
                target_page = inline_ref(container_page, block_id)
                display_target = f"{container_page} / {form.version_name}"
        else:
            generated_title = publisher._configured_release_title(form, index_sync, profile)
            target_page = form.wiki_title or generated_title or form.page_title
            display_target = target_page
            if form.wiki_title:
                page = self.client.get_wiki_page(form.project_id, form.wiki_title)
                if page:
                    old_files = parse_release_files(page.get("text", ""))

        new_files = new_files or []
        if form.wiki_title:
            if form.replace_attachments and not new_files:
                warnings.append("编辑版本未选择新附件，实际更新时会自动保留已有附件列表。")
                attachment_plan = f"保留已有附件 {len(old_files)} 个，不上传新附件"
            elif form.replace_attachments:
                attachment_plan = f"用 {len(new_files)} 个新附件替换旧附件列表"
            else:
                attachment_plan = f"保留已有附件 {len(old_files)} 个，并追加 {len(new_files)} 个新附件"
        else:
            attachment_plan = f"上传 {len(new_files)} 个新附件"
            if not new_files:
                warnings.append("本次发布没有选择附件，Wiki 文件列表会显示为空。")

        plan = {
            "ok": True,
            "mode": mode,
            "action": "编辑版本" if form.wiki_title else "发布新版本",
            "project_id": form.project_id,
            "version_name": form.version_name,
            "release_date": form.release_date,
            "target_page": target_page,
            "wiki_title": target_page,
            "display_target": display_target,
                "container_page": container_page,
                "block_id": block_id,
                "old_block_id": old_block_id,
                "is_edit": is_edit,
                "version_plan": version_plan,
            "version_name_final": version_name_final,
            "attachment_plan": attachment_plan,
            "old_files": old_files,
            "old_files_count": len(old_files),
            "new_files": new_files,
            "files": new_files,
            "notice_enabled": bool(notice_enabled),
            "mail_scope_label": mail_scope_label,
            "mail_to_count": mail_to_count,
            "mail_cc_count": mail_cc_count,
            "warnings": warnings,
        }
        plan["summary_lines"] = self.summary_lines(plan)
        return plan

    def summary_lines(self, plan: dict[str, Any]) -> list[str]:
        lines = [
            f"操作：{plan['action']}",
            f"项目：{plan['project_id']}",
            f"版本：{plan['version_name']}",
            f"日期：{plan['release_date']}",
            f"Wiki 页面：{plan.get('display_target') or plan['target_page']}",
            f"Redmine Version：{plan['version_plan']}",
            f"附件策略：{plan['attachment_plan']}",
        ]
        if plan["new_files"]:
            lines.append("新附件：")
            for item in plan["new_files"]:
                lines.append(f"- {item['filename']} ({_size_text(int(item.get('size') or 0))})")
                if item.get("sha256"):
                    lines.append(f"  SHA256: {item['sha256']}")
        else:
            lines.append("新附件：无")
        if plan["notice_enabled"]:
            lines.append(
                f"邮件：{plan['mail_scope_label']}，收件人 {plan['mail_to_count']} 个，抄送 {plan['mail_cc_count']} 个"
            )
        else:
            lines.append("邮件：不发送")
        if plan["warnings"]:
            lines.append("注意：")
            lines.extend(f"- {item}" for item in plan["warnings"])
        return lines

    def _inline_display_version(self, block_id: str, block: str) -> str:
        if not block:
            return ""
        try:
            parsed = parse_release_page(inline_ref("_", block_id), block)
            return str(parsed.get("version_name") or "").strip()
        except Exception:
            return ""
