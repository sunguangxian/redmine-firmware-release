"""Release Wiki 页面构建与解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PRODUCT_LINES = {
    "常规版本 (5X)": {"key": "Regular", "np500": False},
    "Trunking 集群": {"key": "Trunking", "np500": False},
    "Record 录音": {"key": "Record", "np500": False},
    "NP500": {"key": "NP500", "np500": True},
}


@dataclass
class ReleaseForm:
    project_id: str
    proj_tag: str
    version_name: str
    release_date: str
    commit: str
    product_line: str
    changelog_items: list[str] = field(default_factory=list)
    files: list[tuple[str, str, bytes]] = field(default_factory=list)  # name, desc, bytes
    wiki_title: str | None = None
    replace_attachments: bool = False

    @property
    def product_meta(self) -> dict:
        for label, meta in PRODUCT_LINES.items():
            if label == self.product_line:
                return meta
        if self.product_line == "NP500":
            return PRODUCT_LINES["NP500"]
        return PRODUCT_LINES["常规版本 (5X)"]

    @property
    def wiki_suffix(self) -> str:
        return self.version_name.strip().replace(".", "_")

    @property
    def computed_title(self) -> str:
        tag = self.proj_tag
        if self.product_meta["np500"]:
            return f"Release_{tag}_NP500_FW_{self.wiki_suffix}"
        return f"Release_{tag}_FW_{self.wiki_suffix}"

    @property
    def page_title(self) -> str:
        return self.wiki_title or self.computed_title


def proj_tag_from_project(project_id: str, page_title: str | None = None) -> str:
    if page_title:
        match = re.match(r"^Release_([A-Za-z0-9_+-]+?)(?:_NP500)?_FW_", page_title, re.I)
        if match:
            return match.group(1).upper()
    return project_id.upper()


def build_release_markdown(
    form: ReleaseForm,
    version_id: int | None,
    linked_files: list[dict[str, str | None]],
    main_page: str = "Release_Notes",
) -> str:
    meta = form.product_meta
    title_suffix = (
        f"NP500 FW {form.version_name}" if meta["np500"] else f"FW {form.version_name}"
    )
    changes = "\n".join(f"1. {item}" for item in form.changelog_items) or "（见历史 changelog）"
    ver_link = f"/versions/{version_id}" if version_id else f"/projects/{form.project_id}/roadmap"
    files_link = f"/projects/{form.project_id}/files"
    product_line_block = f"**产品线:** {form.product_line}\n\n" if form.product_line.strip() else ""
    return_page = (main_page or "Release_Notes").strip() or "Release_Notes"

    rows = []
    for item in linked_files:
        name = item.get("filename") or ""
        if not name:
            continue
        desc = item.get("description") or ""
        url = item.get("url")
        cell = f"[{name}]({url})" if url else name
        rows.append(f"| {cell} | {desc} |")
    if not rows:
        rows.append("| （无） | |")

    return (
        f"# Release {form.proj_tag} {title_suffix}\n\n"
        f"{product_line_block}"
        f"**日期:** {form.release_date}\n"
        f"**Commit:** {form.commit}\n\n"
        f"--------------\n\n"
        f"## 变更说明\n\n"
        f"{changes}\n\n"
        f"## 固件文件\n\n"
        f"下载: [版本 {form.version_name}]({ver_link}) | [项目文件]({files_link})\n\n"
        f"| 文件名 | 说明 |\n"
        f"|--------|------|\n"
        f"{chr(10).join(rows)}\n\n"
        f"[[{return_page}|← 返回 Release Notes]]"
    )


def parse_release_files(text: str) -> list[dict[str, str | None]]:
    """解析 Release Wiki 中已有的固件文件表。"""
    files: list[dict[str, str | None]] = []
    section = re.search(r"## 固件文件\s*\n+(.*?)(?:\n## |\Z)", text, re.S)
    if not section:
        return files

    for raw_line in section.group(1).splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line or "文件名" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        file_cell = cells[0]
        if not file_cell or file_cell == "（无）":
            continue
        desc = cells[1] if len(cells) > 1 else ""

        link_match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", file_cell)
        if link_match:
            filename = link_match.group(1).strip()
            url = link_match.group(2).strip()
        else:
            filename = file_cell.strip()
            url = None

        if filename:
            files.append({"filename": filename, "description": desc, "url": url})
    return files


def merge_release_files(
    old_files: list[dict[str, str | None]],
    new_files: list[dict[str, str | None]],
    replace: bool = False,
) -> list[dict[str, str | None]]:
    """合并旧附件和新附件。

    replace=True 只在 Wiki 页面中显示新附件；不会删除 Redmine 项目文件里的旧附件。
    """
    if replace:
        return new_files

    merged: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in old_files + new_files:
        filename = item.get("filename") or ""
        if not filename:
            continue
        key = (filename, item.get("url"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def format_release_files(files: list[dict[str, str | None]]) -> str:
    if not files:
        return "（无已有附件）"
    return "\n".join(
        f"- {item.get('filename') or ''} {item.get('url') or ''}".rstrip()
        for item in files
        if item.get("filename")
    )


def parse_release_page(title: str, text: str) -> dict:
    version_match = re.search(r"# Release \S+(?: NP500)? FW ([^\r\n]+)", text, re.I)
    version_name = version_match.group(1).strip() if version_match else ""
    if not version_name and "_FW_" in title:
        suffix = title.split("_FW_", 1)[1]
        version_name = "V" + suffix.replace("_", ".").lstrip("Vv")

    date_match = re.search(r"\*\*日期:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    release_date = date_match.group(1) if date_match else ""

    commit_match = re.search(r"\*\*Commit:\*\*\s*([^\r\n]+)", text)
    commit = commit_match.group(1).strip() if commit_match else ""

    product_match = re.search(r"\*\*产品线:\*\*\s*([^\r\n]+)", text)
    if product_match:
        product_line = product_match.group(1).strip()
    elif "_NP500_FW_" in title:
        product_line = "NP500"
    elif re.search(r"^V5\.4\.7\.", version_name, re.I):
        product_line = "Trunking 集群"
    elif re.search(r"Record|录音", commit) or re.search(r"录音", text):
        product_line = "Record 录音"
    else:
        product_line = ""

    changelog = []
    section = re.search(r"## 变更说明\s*\n+(.*?)(?:\n## |\Z)", text, re.S)
    if section:
        for line in section.group(1).splitlines():
            line = re.sub(r"^\d+\.\s*", "", line.strip())
            if line:
                changelog.append(line)

    files = parse_release_files(text)

    return {
        "version_name": version_name,
        "release_date": release_date,
        "commit": commit,
        "product_line": product_line,
        "changelog": "\n".join(changelog),
        "files": files,
    }
