"""项目 Release Wiki 结构配置页解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CONFIG_PAGE_TITLE = "Release_Tool_Config"
CONFIG_BEGIN = "<!-- RELEASE_CONFIG_BEGIN -->"
CONFIG_END = "<!-- RELEASE_CONFIG_END -->"


@dataclass
class ConfigCategory:
    key: str
    title: str = ""
    hub_page: str = ""
    list_page: str = ""


@dataclass
class ReleaseWikiConfig:
    mode: str = ""
    main_page: str = ""
    release_page_prefix: str = ""
    categories: list[ConfigCategory] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        if self.mode not in {"single_list", "multi_list"}:
            return False
        if not self.main_page:
            return False
        if self.mode == "multi_list" and not self.categories:
            return False
        return True


def parse_release_wiki_config(text: str) -> ReleaseWikiConfig | None:
    """从 Release_Tool_Config 页面解析工具配置。

    这里故意不依赖 PyYAML，避免额外安装依赖；只解析模板中用到的简单 YAML 子集。
    """
    block = _extract_config_block(text)
    if not block:
        return None

    lines = [_strip_comment(line.rstrip()) for line in block.splitlines()]
    config = ReleaseWikiConfig()
    current_category: ConfigCategory | None = None
    in_categories = False

    for raw in lines:
        if not raw.strip():
            continue
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            continue

        if stripped == "categories:":
            in_categories = True
            current_category = None
            continue

        if stripped.startswith("- ") and in_categories:
            current_category = ConfigCategory(key="")
            config.categories.append(current_category)
            rest = stripped[2:].strip()
            if rest:
                key, value = _split_key_value(rest)
                if key:
                    _assign_category(current_category, key, value)
            continue

        key, value = _split_key_value(stripped)
        if not key:
            continue

        if in_categories and current_category is not None and raw.startswith((" ", "\t")):
            _assign_category(current_category, key, value)
        else:
            in_categories = False
            if key == "mode":
                config.mode = value
            elif key == "main_page":
                config.main_page = value
            elif key == "release_page_prefix":
                config.release_page_prefix = value

    config.categories = [c for c in config.categories if c.key]
    return config if config.is_valid else None


def _extract_config_block(text: str) -> str:
    marker = re.search(
        rf"{re.escape(CONFIG_BEGIN)}(.*?){re.escape(CONFIG_END)}",
        text,
        flags=re.S,
    )
    if marker:
        return _strip_fence(marker.group(1).strip())

    # 兼容只放一个 yaml 代码块的页面。
    fence = re.search(r"```(?:yaml|yml)?\s*(.*?)```", text, flags=re.S | re.I)
    return _strip_fence(fence.group(1).strip()) if fence else ""


def _strip_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:yaml|yml)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _strip_comment(line: str) -> str:
    if "#" not in line:
        return line
    # 只处理行首注释，避免中文说明里的 # 被误删。
    return "" if line.lstrip().startswith("#") else line


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        return "", ""
    key, value = line.split(":", 1)
    return key.strip(), _unquote(value.strip())


def _unquote(value: str) -> str:
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _assign_category(category: ConfigCategory, key: str, value: str) -> None:
    if key == "key":
        category.key = value
    elif key == "title":
        category.title = value
    elif key in {"hub_page", "hub"}:
        category.hub_page = value
    elif key in {"list_page", "list"}:
        category.list_page = value
