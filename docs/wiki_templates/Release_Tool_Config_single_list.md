# Release Tool Config - 单列表结构模板

将本页面内容复制到项目 Wiki 页面：`Release_Tool_Config`。

适用项目：TP35 这类只有一个 Release 列表页的项目。

## Wiki 结构图

```text
Release_Notes
├── Release_TP35_FW_V1_00_00_0030_20260320
├── Release_TP35_FW_V1_0_0_29
└── Release_TP35_FW_V5_3_7_14
```

## 工具配置

请勿删除 `RELEASE_CONFIG_BEGIN` / `RELEASE_CONFIG_END` 之间的内容。

<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
release_page_prefix: Release_TP35_FW_
```
<!-- RELEASE_CONFIG_END -->

## 页面说明

- `mode: single_list` 表示所有 Release 页面统一写入一个版本列表页。
- `main_page` 是工具要自动更新的主版本列表页。
- `release_page_prefix` 仅用于说明当前项目的 Release 页面命名习惯，当前工具主要根据 `Release_..._FW_...` 识别版本页。

## Release_Notes 页面建议内容

```text
# Release Notes

本页面记录当前项目固件发布历史。

## 版本列表

<!-- RELEASE_SYNC_BEGIN -->
工具会自动生成版本列表
<!-- RELEASE_SYNC_END -->
```
