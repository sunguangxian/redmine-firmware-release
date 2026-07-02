# Release Tool Config - 多分类 include 结构模板

将本页面内容复制到项目 Wiki 页面：`Release_Tool_Config`。

适用项目：DP5X 这类有主页面、产品线页面，并且产品线页面通过 `{{include(...)}}` 引入独立列表页的结构。

## Wiki 结构图

```text
Changelog_for_5X
├── Release_Notes_Regular
│   └── {{include(Release_Notes_Regular_List)}}
├── Release_Notes_Trunking
│   └── {{include(Release_Notes_Trunking_List)}}
├── Release_Notes_Record
│   └── {{include(Release_Notes_Record_List)}}
└── Release_Notes_NP500
    └── {{include(Release_Notes_NP500_List)}}
```

## 工具配置

请勿删除 `RELEASE_CONFIG_BEGIN` / `RELEASE_CONFIG_END` 之间的内容。

<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: multi_list
main_page: Changelog_for_5X
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

## 主页面建议内容

`Changelog_for_5X`：

```text
# Changelog for 5X

## 产品线索引

<!-- RELEASE_SYNC_BEGIN -->
工具会自动生成产品线索引和 include 区域
<!-- RELEASE_SYNC_END -->
```

## 产品线页面建议内容

例如 `Release_Notes_Regular`：

```text
# 常规版本 (5X)

[[Changelog_for_5X|返回主页面]]

## 版本列表

{{include(Release_Notes_Regular_List)}}
```

## 列表页建议内容

例如 `Release_Notes_Regular_List`：

```text
<!-- RELEASE_SYNC_BEGIN -->
工具会自动生成版本列表
<!-- RELEASE_SYNC_END -->
```
