"""Release_Tool_Config 页面模板。"""

from __future__ import annotations

from .wiki_config import CONFIG_BEGIN, CONFIG_END, parse_release_wiki_config

TEMPLATE_CHOICES = [
    ("单列表：Release_Notes", "single_list"),
    ("多分类：include 独立列表页", "multi_list_include"),
    ("多分类：直接更新分类页", "multi_list_direct"),
]


def build_config_template(template_key: str, project_id: str = "") -> str:
    tag = (project_id or "TP35").upper()
    if template_key == "multi_list_include":
        return _multi_list_include_template()
    if template_key == "multi_list_direct":
        return _multi_list_direct_template()
    return _single_list_template(tag)


def validate_config_text(text: str) -> tuple[bool, str]:
    config = parse_release_wiki_config(text or "")
    if not config:
        return False, "配置无效：请检查 RELEASE_CONFIG_BEGIN / RELEASE_CONFIG_END 之间的内容。"
    if config.mode == "single_list":
        return True, f"配置有效：single_list，主页面 {config.main_page}。"
    lines = [f"配置有效：multi_list，主页面 {config.main_page}。", "分类："]
    for item in config.categories:
        list_page = item.list_page or item.hub_page
        lines.append(f"- {item.key}: {item.title or item.key}, hub={item.hub_page}, list={list_page}")
    return True, "\n".join(lines)


def _single_list_template(tag: str) -> str:
    return f"""# Release Tool Config

本页面用于配置当前项目的 Release Wiki 结构。

## Wiki 结构图

```text
Release_Notes
├── Release_{tag}_FW_V1_0_0_1
└── Release_{tag}_FW_V1_0_0_2
```

## 工具配置

请勿删除 RELEASE_CONFIG_BEGIN / RELEASE_CONFIG_END 之间的内容。

{CONFIG_BEGIN}
```yaml
mode: single_list
main_page: Release_Notes
release_page_prefix: Release_{tag}_FW_
```
{CONFIG_END}

## 页面生成规则

- Release_Notes 为主页面，工具自动维护完整版本列表。
- Release 明细页会自动挂到 Release_Notes 父页面下。
"""


def _multi_list_include_template() -> str:
    return f"""# Release Tool Config

本页面用于配置当前项目的 Release Wiki 结构。

## Wiki 结构图

```text
Changelog_for_5X
└── {{include(Release_Notes)}}

Release_Notes
├── Release_Notes_Regular -> {{include(Release_Notes_Regular_List)}}
├── Release_Notes_Trunking -> {{include(Release_Notes_Trunking_List)}}
├── Release_Notes_Record -> {{include(Release_Notes_Record_List)}}
└── Release_Notes_NP500 -> {{include(Release_Notes_NP500_List)}}
```

## 工具配置

请勿删除 RELEASE_CONFIG_BEGIN / RELEASE_CONFIG_END 之间的内容。

{CONFIG_BEGIN}
```yaml
mode: multi_list
main_page: Release_Notes
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular_List

  - key: Trunking
    title: Trunking 集群
    hub_page: Release_Notes_Trunking
    list_page: Release_Notes_Trunking_List

  - key: Record
    title: Record 录音
    hub_page: Release_Notes_Record
    list_page: Release_Notes_Record_List

  - key: NP500
    title: NP500
    hub_page: Release_Notes_NP500
    list_page: Release_Notes_NP500_List
```
{CONFIG_END}

## 页面生成规则

- Changelog_for_5X 仅作为旧入口，内容为 `{{include(Release_Notes)}}`。
- Release_Notes 为主页面，工具自动生成分类入口和每类最近版本。
- Release_Notes_xxx 为分类页，工具自动生成固定结构。
- Release_Notes_xxx_List 为完整列表页，工具自动维护列表内容。
"""


def _multi_list_direct_template() -> str:
    return f"""# Release Tool Config

本页面用于配置当前项目的 Release Wiki 结构。

## Wiki 结构图

```text
Changelog_for_5X
├── Release_Notes_Regular
├── Release_Notes_Trunking
├── Release_Notes_Record
└── Release_Notes_NP500
```

## 工具配置

请勿删除 RELEASE_CONFIG_BEGIN / RELEASE_CONFIG_END 之间的内容。

{CONFIG_BEGIN}
```yaml
mode: multi_list
main_page: Release_Notes
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular

  - key: Trunking
    title: Trunking 集群
    hub_page: Release_Notes_Trunking
    list_page: Release_Notes_Trunking

  - key: Record
    title: Record 录音
    hub_page: Release_Notes_Record
    list_page: Release_Notes_Record

  - key: NP500
    title: NP500
    hub_page: Release_Notes_NP500
    list_page: Release_Notes_NP500
```
{CONFIG_END}
"""
