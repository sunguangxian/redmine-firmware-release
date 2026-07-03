# Release Tool Config - 单列表结构模板

将本页面内容复制到项目 Wiki 页面：`Release_Tool_Config`。

适用项目：TP35 这类只有一个 Release 分类，主页面直接显示完整版本列表的项目。

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

## 页面生成规则

- `Release_Notes` 为主页面，工具自动维护完整版本列表。
- Release 明细页会自动挂到 `Release_Notes` 父页面下。
