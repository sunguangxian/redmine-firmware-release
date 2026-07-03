# Release Tool Config - 多分类直接列表结构模板

将本页面内容复制到项目 Wiki 页面：`Release_Tool_Config`。

适用项目：有多个产品线页面，但不单独拆 `xxx_List` 页面，工具直接更新产品线页面中的“版本列表”章节。

## Wiki 结构图

```text
Changelog_for_5X
├── Release_Notes_Regular
├── Release_Notes_Trunking
├── Release_Notes_Record
└── Release_Notes_NP500
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
<!-- RELEASE_CONFIG_END -->

## 主页面建议内容

`Changelog_for_5X`：

```text
# Changelog for 5X

## 产品线索引

<!-- RELEASE_SYNC_BEGIN -->
工具会自动生成产品线索引和分类摘要
<!-- RELEASE_SYNC_END -->
```

## 产品线页面建议内容

例如 `Release_Notes_Trunking`：

```text
# Trunking 集群

[[Changelog_for_5X|返回主页面]]

## 版本列表

<!-- RELEASE_SYNC_BEGIN -->
工具会自动生成版本列表
<!-- RELEASE_SYNC_END -->
```
