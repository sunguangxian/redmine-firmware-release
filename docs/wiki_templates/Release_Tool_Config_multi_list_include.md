# Release Tool Config - 多分类固定结构模板

将本页面内容复制到项目 Wiki 页面：`Release_Tool_Config`。

适用项目：DP5X 这类有多个产品线分类，并且希望主页面只显示分类入口和每类最近版本，完整列表放在独立 `_List` 页面中的项目。

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

请勿删除 `RELEASE_CONFIG_BEGIN` / `RELEASE_CONFIG_END` 之间的内容。

<!-- RELEASE_CONFIG_BEGIN -->
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
<!-- RELEASE_CONFIG_END -->

## 页面生成规则

- `Changelog_for_5X` 仅作为旧入口，内容为 `{{include(Release_Notes)}}`。
- `Release_Notes` 为主页面，工具自动生成分类入口和每类最近版本。
- `Release_Notes_xxx` 为分类页，工具自动生成固定结构。
- `Release_Notes_xxx_List` 为完整列表页，工具自动维护列表内容。
- 发布或刷新索引时，工具会自动设置分类页、列表页和 Release 明细页的父页面关系。
