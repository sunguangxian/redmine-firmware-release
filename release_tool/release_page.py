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
        f"# {_version_heading_markdown(form.project_id, form.version_name, version_id, form.release_date)}\n\n"
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
    return (
        f"{INLINE_BEGIN_PREFIX}{marker} -->\n"
        f"## {_inline_version_heading_text(version, form.release_date)}\n\n"
        f"{_release_body_markdown(form, version_id, linked_files, heading_level=0)}"
        f"\n"
        f"{INLINE_END_PREFIX}{marker} -->"
    )


def _version_heading_markdown(
    project_id: str,
    version_name: str,
    version_id: int | None,
    release_date: str = "",
) -> str:
    version = (version_name or "").strip()
    date = (release_date or "").strip()
    suffix = f" ({date})" if date else ""
    return f"[{version}]({version_or_roadmap_link(project_id, version_id)}){suffix}" if version else ""


def _version_heading_text(version_name: str, release_date: str = "") -> str:
    version = (version_name or "").strip()
    date = (release_date or "").strip()
    suffix = f" ({date})" if date else ""
    return f"{version}{suffix}" if version else ""


def _inline_version_heading_text(version_name: str, release_date: str = "") -> str:
    version = (version_name or "").strip()
    if not version:
        return ""
    return f"version:{_version_heading_text(version, release_date)}"


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
    text = normalize_inline_release_page(page_text or "")
    pattern = _inline_block_pattern(block_id)
    if pattern.search(text):
        base = pattern.sub("", text, count=1)
        return normalize_inline_release_page(_append_inline_release_block(base, block))
    base = text.rstrip()
    if not base:
        base = _ensure_inline_toc("# Release Notes\n\n固件版本发布记录。")
    return normalize_inline_release_page(_append_inline_release_block(base, block))


def normalize_inline_release_page(page_text: str) -> str:
    text = _normalize_inline_toc(_ensure_inline_toc(page_text or ""))
    return _sort_inline_release_blocks(_remove_version_list_heading(_normalize_inline_block_headings(text)))


def _normalize_inline_toc(page_text: str) -> str:
    seen = False

    def repl(match: re.Match[str]) -> str:
        nonlocal seen
        if seen:
            return ""
        seen = True
        return "\n{{>toc}}\n"

    return re.sub(r"(?m)^\s*\{\{>toc\}\}\s*$", repl, page_text or "")


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
        body = _remove_inline_heading_version_link(body)
        body = _remove_inline_internal_separator(body)
        body = _remove_inline_migration_source(body)
        body = re.sub(r"^#{2,6}\s+(变更说明|固件文件|迁移来源)\s*$", r"**\1**", body, flags=re.M)
        return f"{match.group(1)}\n{body.strip()}\n{match.group(3)}"

    return pattern.sub(repl, page_text or "")


def _remove_version_list_heading(page_text: str) -> str:
    return re.sub(r"(?m)^\s*#{2,6}\s+版本列表\s*\r?\n+", "", page_text or "")


def _sort_inline_release_blocks(page_text: str) -> str:
    category_matches = list(re.finditer(r"(?m)^##\s+(?!version:)[^\r\n]+\s*$", page_text or "", re.I))
    if category_matches:
        parts: list[str] = []
        boundaries = [0] + [match.start() for match in category_matches] + [len(page_text or "")]
        for idx in range(len(boundaries) - 1):
            parts.append(_sort_inline_release_blocks_segment((page_text or "")[boundaries[idx] : boundaries[idx + 1]]))
        return "".join(parts).rstrip() + "\n"
    return _sort_inline_release_blocks_segment(page_text)


def _sort_inline_release_blocks_segment(page_text: str) -> str:
    pattern = re.compile(
        rf"{re.escape(INLINE_BEGIN_PREFIX)}(?P<block_id>.*?)\s*-->.*?{re.escape(INLINE_END_PREFIX)}(?P=block_id)\s*-->",
        re.S,
    )
    matches = list(pattern.finditer(page_text or ""))
    if len(matches) < 2:
        return page_text

    prefix = page_text[: matches[0].start()].rstrip()
    suffix = page_text[matches[-1].end() :].strip()
    blocks = [match.group(0).strip() for match in matches]
    ordered = sorted(blocks, key=_inline_block_sort_key, reverse=True)
    result = prefix + "\n\n" + "\n\n--------------\n\n".join(ordered)
    if suffix:
        result += "\n\n" + suffix
    return result.rstrip() + "\n"


def _append_inline_release_block(page_text: str, block: str) -> str:
    base = (page_text or "").rstrip()
    insert_at = _matching_inline_category_insert_position(base, block)
    if insert_at is None:
        return base + "\n\n" + block + "\n"
    return base[:insert_at].rstrip() + "\n\n" + block + "\n\n" + base[insert_at:].lstrip()


def _matching_inline_category_insert_position(page_text: str, block: str) -> int | None:
    parsed = parse_release_page("", block)
    version = parsed.get("version_name") or ""
    if not version:
        return None
    category_matches = list(re.finditer(r"(?m)^##\s+(?P<title>(?!version:)[^\r\n]*V(?P<prefix>\d+(?:\.\d+)*)\.X[^\r\n]*)$", page_text or "", re.I))
    for idx, match in enumerate(category_matches):
        prefix = "V" + match.group("prefix") + "."
        if not version.upper().startswith(prefix.upper()):
            continue
        return category_matches[idx + 1].start() if idx + 1 < len(category_matches) else len(page_text or "")
    return None


def _inline_block_sort_key(block: str) -> tuple[str, tuple[int, ...], str]:
    parsed = parse_release_page("", block)
    version = parsed.get("version_name") or ""
    return parsed.get("release_date") or "0000-01-01", _version_sort_tuple(version), version


def _version_sort_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version or ""))


def _remove_inline_migration_source(block_body: str) -> str:
    cleaned = re.sub(
        r"\n{0,2}(?:\*\*[^\r\n]*(?:迁移来源|Migration Source|杩佺Щ)[^\r\n]*\*\*|#{2,6}\s+[^\r\n]*(?:迁移来源|Migration Source|杩佺Щ)[^\r\n]*)\s*\n+(?:-\s+\[\[[^\]]+\]\]\s*\n?)+",
        "\n",
        block_body or "",
    )
    return cleaned.strip()


def _remove_inline_internal_separator(block_body: str) -> str:
    return re.sub(
        r"(?m)(^\*\*Commit:\*\*[^\r\n]*(?:\r?\n)+)(?:[ \t]*\r?\n)*-{3,}[ \t]*(?:\r?\n)+",
        r"\1\n",
        block_body or "",
    )


def _remove_inline_heading_version_link(block_body: str) -> str:
    block_body = re.sub(
        r"(?m)^((?:##|###)\s+(?:version:)?V[^\r\n]+)[ \t]*\r?\n(?:[ \t]*\r?\n)*\[[^\]\r\n]*V[^\]\r\n]*\]\([^)]+\)[ \t]*(?:\r?\n)+",
        r"\1\n\n",
        block_body or "",
    )
    return re.sub(
        r"(?m)^(##\s+(?:version:)?V[^\r\n]+)[ \t]*\r?\n(?:[ \t]*\r?\n)*\[版本\s+[^\]\r\n]+\]\([^)]+\)[ \t]*(?:\r?\n)+",
        r"\1\n\n",
        block_body or "",
    )


def _link_inline_release_heading(block_body: str) -> str:
    version_macro_heading = re.search(
        r"^(?P<level>#{2,3})\s+version:(V[^\s\r\n]+)(?P<date>\s+\(\d{4}-\d{2}-\d{2}\))?\s*$",
        block_body,
        re.I | re.M,
    )
    if version_macro_heading:
        version = version_macro_heading.group(2).strip()
        date = version_macro_heading.group("date") or ""
        replacement = f"{version_macro_heading.group('level')} version:{version}{date}"
        return block_body[: version_macro_heading.start()] + replacement + block_body[version_macro_heading.end() :]

    plain_version_heading = re.search(
        r"^(?P<level>#{2,3})\s+(V[^\s\r\n]+)(?P<date>\s+\(\d{4}-\d{2}-\d{2}\))?\s*$",
        block_body,
        re.I | re.M,
    )
    if plain_version_heading:
        version = plain_version_heading.group(2).strip()
        date = plain_version_heading.group("date") or ""
        replacement = f"{plain_version_heading.group('level')} version:{version}{date}"
        return block_body[: plain_version_heading.start()] + replacement + block_body[plain_version_heading.end() :]

    linked_plain_heading = re.search(
        r"^(?P<level>#{2,3})\s+\[([^\]\r\n]+)\]\(([^)]+)\)\s*(?P<date>\(\d{4}-\d{2}-\d{2}\))?\s*$",
        block_body,
        re.I | re.M,
    )
    if linked_plain_heading:
        version = linked_plain_heading.group(2).strip()
        release_name = re.match(r"Release\s+\S+(?:\s+NP500)?\s+FW\s+(.+)", version, re.I)
        if release_name:
            version = release_name.group(1).strip()
        date = f" {linked_plain_heading.group('date')}" if linked_plain_heading.group("date") else ""
        replacement = f"{linked_plain_heading.group('level')} version:{version}{date}"
        return block_body[: linked_plain_heading.start()] + replacement + block_body[linked_plain_heading.end() :]

    linked_heading = re.search(
        r"^(?P<level>#{2,3})\s+\[Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\]\r\n]+)\]\(([^)]+)\)\s*$",
        block_body,
        re.I | re.M,
    )
    if linked_heading:
        version = linked_heading.group(2).strip()
        return block_body[: linked_heading.start()] + f"{linked_heading.group('level')} version:{version}" + block_body[linked_heading.end() :]

    heading = re.search(r"^(?P<level>#{2,3})\s+(?!\[)(Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\r\n]+))\s*$", block_body, re.I | re.M)
    if not heading:
        return block_body
    version = heading.group(3).strip()
    return block_body[: heading.start()] + f"{heading.group('level')} version:{version}" + block_body[heading.end() :]


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
    internal_separator = "" if not heading else "\n--------------\n"
    return (
        f"**日期:** {form.release_date}\n"
        f"**Commit:** {form.commit}\n\n"
        f"{internal_separator}\n"
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
    version_match = re.search(r"^#{1,3}\s+version:\s*(V[^\s\r\n]+)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,3}\s+Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\r\n]+)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,3}\s+\[Release\s+\S+(?:\s+NP500)?\s+FW\s+([^\]\r\n]+)\]\([^)]+\)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,3}\s+\[([^\]\r\n]+)\]\([^)]+\)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{1,3}\s+(V[^\s\r\n]+)", text, re.I | re.M)
    if not version_match:
        version_match = re.search(r"^#{2,3}\s+([^\s(]+)\s*\((\d{4}-\d{2}-\d{2})\)", text, re.I | re.M)
    version_name = version_match.group(1).strip() if version_match else ""
    inline = parse_inline_ref(title)
    if not version_name and inline:
        version_name = inline[1]
    if not version_name and "_FW_" in title:
        suffix = title.split("_FW_", 1)[1]
        version_name = "V" + suffix.replace("_", ".").lstrip("Vv")

    date_match = re.search(r"\*\*日期:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if not date_match:
        date_match = re.search(r"^#{2,3}\s+(?:version:)?[^\s(]+\s*\((\d{4}-\d{2}-\d{2})\)", text, re.I | re.M)
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
