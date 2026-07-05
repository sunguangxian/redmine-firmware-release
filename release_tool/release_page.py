"""Release Wiki 页面构建与解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

PRODUCT_LINES = {
    "常规版本 (5X)": {"key": "Regular", "np500": False},
    "Trunking 集群": {"key": "Trunking", "np500": False},
    "Record 录音": {"key": "Record", "np500": False},
    "NP500": {"key": "NP500", "np500": True},
}

INLINE_REF_PREFIX = "INLINE::"
INLINE_BEGIN_PREFIX = "<!-- RELEASE_INLINE_BEGIN:"
INLINE_END_PREFIX = "<!-- RELEASE_INLINE_END:"


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
        inline = parse_inline_ref(page_title)
        if inline:
            return project_id.upper()
        match = re.match(r"^Release_([A-Za-z0-9_+-]+?)(?:_NP500)?_FW_", page_title, re.I)
        if match:
            return match.group(1).upper()
    return project_id.upper()


def inline_ref(container_page: str, block_id: str) -> str:
    return f"{INLINE_REF_PREFIX}{quote(container_page or '', safe='')}::{quote(block_id or '', safe='')}"


def parse_inline_ref(value: str | None) -> tuple[str, str] | None:
    text = value or ""
    if not text.startswith(INLINE_REF_PREFIX):
        return None
    rest = text[len(INLINE_REF_PREFIX):]
    parts = rest.split("::", 1)
    if len(parts) != 2:
        return None
    page = unquote(parts[0]).strip()
    block_id = unquote(parts[1]).strip()
    if not page or not block_id:
        return None
    return page, block_id


def release_anchor(version_name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", (version_name or "").strip().lower()).strip("-") or "release"


def project_path(project_id: str, suffix: str = "") -> str:
    normalized_suffix = suffix if suffix.startswith("/") or not suffix else f"/{suffix}"
    return f"/projects/{quote(project_id or '', safe='')}{normalized_suffix}"


def version_or_roadmap_link(project_id: str, version_id: int | None) -> str:
    if version_id:
        return f"/versions/{version_id}"
    return project_path(project_id, "/roadmap")


def build_release_markdown(
    form: ReleaseForm,
    version_id: int | None,
    linked_files: list[dict[str, str | None]],
    main_page: str = "Release_Notes",
) -> str:
    return (
        f"# {_version_heading_markdown(form.project_id, form.version_name, version_id)}\n\n"
        f"{_release_body_markdown(form, version_id, linked_files)}\n\n"
        f"[[{(main_page or 'Release_Notes').strip() or 'Release_Notes'}|← 返回 Release Notes]]"
    )


def build_inline_release_block(
    form: ReleaseForm,
    version_id: int | None,
    linked_files: list[dict[str, str | None]],
    source_page: str = "",
    block_id: str | None = None,
    display_version: str | None = None,
    container_page: str = "",
) -> str:
    marker = inline_block_id(block_id or form.version_name)
    version = (display_version or form.version_name).strip()
    source = f"\n\n**迁移来源**\n\n- [[{source_page}]]" if source_page else ""
    return (
        f"{INLINE_BEGIN_PREFIX}{marker} -->\n"
        f"## {_version_heading_markdown(form.project_id, version, version_id)}\n\n"
        f"{_release_body_markdown(form, version_id, linked_files, heading_level=0)}"
        f"{source}\n"
        f"{INLINE_END_PREFIX}{marker} -->"
    )


def _version_heading_markdown(project_id: str, version_name: str, version_id: int | None) -> str:
    version = (version_name or "").strip()
    return f"[{version}]({version_or_roadmap_link(project_id, version_id)})" if version else ""


def inline_block_id(version_name: str) -> str:
    return (version_name or "").strip()


def _inline_block_pattern(block_id: str, capture_body: bool = False) -> re.Pattern[str]:
    marker = inline_block_id(block_id)
    middle = "(?P<body>.*?)" if capture_body else ".*?"
    return re.compile(
        rf"{re.escape(INLINE_BEGIN_PREFIX)}{re.escape(marker)}\s*-->{middle}{re.escape(INLINE_END_PREFIX)}{re.escape(marker)}\s*-->",
        re.S,
    )


def replace_inline_release_block(page_text: str, block_id: str, block: str) -> str:
    text = _remove_version_list_heading(_normalize_inline_block_headings(_ensure_inline_toc(page_text or "")))
    pattern = _inline_block_pattern(block_id)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    base = text.rstrip()
    if not base:
        base = _ensure_inline_toc("# Release Notes\n\n固件版本发布记录。")
    return base.rstrip() + "\n\n" + block + "\n"


def _ensure_inline_toc(page_text: str) -> str:
    text = page_text or ""
    if "{{>toc}}" in text:
        return text
    if not text.strip():
        return "# Release Notes\n\n{{>toc}}\n\n固件版本发布记录。"
    heading = re.match(r"(?P<head>\s*#\s+[^\r\n]+)(?P<rest>.*)", text, re.S)
    if heading:
        return f"{heading.group('head')}\n\n{{{{>toc}}}}\n{heading.group('rest')}"
    return f"{{{{>toc}}}}\n\n{text}"


def _normalize_inline_block_headings(page_text: str) -> str:
    pattern = re.compile(
        rf"({re.escape(INLINE_BEGIN_PREFIX)}.*?\s*-->)(?P<body>.*?)({re.escape(INLINE_END_PREFIX)}.*?\s*-->)",
        re.S,
    )

    def repl(match: re.Match[str]) -> str:
        body = match.group("body")
        body = _link_inline_release_heading(body)
        body = re.sub(r"^#{2,6}\s+(变更说明|固件文件|迁移来源)\s*$", r"**\1**", body, flags=re.M)
        return f"{match.group(1)}{body}{match.group(3)}"

    return pattern.sub(repl, page_text or "")


def _remove_version_list_heading(page_text: str) -> str:
    return re.sub(r"(?m)^\s*#{2,6}\s+版本列表\s*\r?\n+", "", page_text or "")


def _link_inline_release_heading(block_body: str) -> str:
    linked_heading = re.search(
        r"^##\s+\[Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\]\r\n]+)\]\(([^)]+)\)\s*$",
        block_body,
        re.I | re.M,
    )
    if linked_heading:
        version = linked_heading.group(1).strip()
        url = linked_heading.group(2).strip()
        return block_body[: linked_heading.start()] + f"## [{version}]({url})" + block_body[linked_heading.end() :]

    heading = re.search(r"^##\s+(?!\[)(Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\r\n]+))\s*$", block_body, re.I | re.M)
    if not heading:
        return block_body
    version = heading.group(2).strip()
    link = re.search(rf"\[版本\s+{re.escape(version)}\]\(([^)]+)\)", block_body)
    if not link:
        return block_body
    return block_body[: heading.start()] + f"## [{version}]({link.group(1)})" + block_body[heading.end() :]


def delete_inline_release_block(page_text: str, block_id: str) -> str:
    text = page_text or ""
    if not block_id:
        return text
    return _inline_block_pattern(block_id).sub("", text, count=1).rstrip() + ("\n" if text else "")


def extract_inline_release_block(page_text: str, block_id: str) -> str:
    pattern = _inline_block_pattern(block_id, capture_body=True)
    match = pattern.search(page_text or "")
    return match.group("body").strip() if match else ""


def parse_inline_releases(page_text: str, container_page: str) -> list[dict]:
    result: list[dict] = []
    pattern = re.compile(
        rf"{re.escape(INLINE_BEGIN_PREFIX)}(?P<block_id>.*?)\s*-->(?P<body>.*?){re.escape(INLINE_END_PREFIX)}(?P=block_id)\s*-->",
        re.S,
    )
    for match in pattern.finditer(page_text or ""):
        block_id = match.group("block_id").strip()
        body = match.group("body").strip()
        parsed = parse_release_page(inline_ref(container_page, block_id), body)
        version = parsed.get("version_name") or block_id
        if not parsed.get("version_name"):
            parsed["version_name"] = version
        result.append(
            {
                "title": inline_ref(container_page, block_id),
                "container_page": container_page,
                "block_id": block_id,
                "version": version,
                "date": parsed.get("release_date") or "0000-01-01",
                "product_line": parsed.get("product_line") or "",
                "summary": (parsed.get("changelog", "").splitlines() or [""])[0],
                "text": body,
                "files": parsed.get("files", []),
            }
        )
    return result


def _release_body_markdown(
    form: ReleaseForm,
    version_id: int | None,
    linked_files: list[dict[str, str | None]],
    heading_level: int = 2,
) -> str:
    heading = "#" * max(1, min(6, int(heading_level))) if heading_level else ""
    changes_title = f"{heading} 变更说明" if heading else "**变更说明**"
    files_title = f"{heading} 固件文件" if heading else "**固件文件**"
    changes = "\n".join(f"1. {item}" for item in form.changelog_items) or "（见历史 changelog）"
    ver_link = version_or_roadmap_link(form.project_id, version_id)
    files_link = project_path(form.project_id, "/files")
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
        f"**日期:** {form.release_date}\n"
        f"**Commit:** {form.commit}\n\n"
        f"--------------\n\n"
        f"{changes_title}\n\n"
        f"{changes}\n\n"
        f"{files_title}\n\n"
        f"下载: [版本 {form.version_name}]({ver_link}) | [项目文件]({files_link})\n\n"
        f"| 文件名 | 说明 |\n"
        f"|--------|------|\n"
        f"{chr(10).join(rows)}"
    )


def parse_release_files(text: str) -> list[dict[str, str | None]]:
    """解析 Release Wiki 中已有的固件文件表。"""
    files: list[dict[str, str | None]] = []
    section = re.search(r"^#{2,6}\s+固件文件\s*\n+(.*?)(?:\n#{1,6}\s+|\Z)", text, re.S | re.M)
    if not section:
        section = re.search(r"^\*\*固件文件\*\*\s*\n+(.*?)(?:\n\*\*迁移来源\*\*|\n#{1,6}\s+|\Z)", text, re.S | re.M)
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
    version_match = re.search(r"^#{1,2}\s+Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\r\n]+)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,2}\s+\[Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\]\r\n]+)\]\([^)]+\)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,2}\s+\[([^\]\r\n]+)\]\([^)]+\)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,2}\s+(V[^\s\r\n]+)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^##\s+([^\s(]+)\s*\((\d{4}-\d{2}-\d{2})\)", text, re.I | re.M)
    version_name = version_match.group(1).strip() if version_match else ""
    inline = parse_inline_ref(title)
    if not version_name and inline:
        version_name = inline[1]
    if not version_name and "_FW_" in title:
        suffix = title.split("_FW_", 1)[1]
        version_name = "V" + suffix.replace("_", ".").lstrip("Vv")

    date_match = re.search(r"\*\*日期:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if not date_match:
        date_match = re.search(r"^##\s+[^\s(]+\s*\((\d{4}-\d{2}-\d{2})\)", text, re.M)
    release_date = date_match.group(1) if date_match else ""

    commit_match = re.search(r"\*\*Commit:\*\*\s*([^\r\n]+)", text)
    commit = commit_match.group(1).strip() if commit_match else ""

    product_match = re.search(r"\*\*产品线:\*\*\s*([^\r\n]+)", text)
    if product_match:
        product_line = product_match.group(1).strip()
    elif "_NP500_FW_" in title:
        product_line = "NP500"
    elif "_FW_" in title:
        prefix = title.split("_FW_", 1)[0]
        product_line = prefix.rsplit("_", 1)[-1].replace("_", " ").strip()
    elif re.search(r"^V5\.4\.7\.", version_name, re.I):
        product_line = "Trunking 集群"
    elif re.search(r"Record|录音", commit) or re.search(r"录音", text):
        product_line = "Record 录音"
    else:
        product_line = ""

    changelog = []
    section = re.search(r"^#{2,6}\s+变更说明\s*\n+(.*?)(?:\n#{1,6}\s+|\Z)", text, re.S | re.M)
    if not section:
        section = re.search(r"^\*\*变更说明\*\*\s*\n+(.*?)(?:\n\*\*固件文件\*\*|\n#{1,6}\s+|\Z)", text, re.S | re.M)
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
