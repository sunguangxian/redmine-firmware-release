# 测试与基础验证

当前项目先使用 Python 标准库 `unittest` 编写后端核心逻辑测试，避免额外引入测试依赖。

## 运行语法检查

```bash
python -m compileall release_tool tests
```

## 运行单元测试

```bash
python -m unittest discover -s tests
```

## 建议重点验证场景

1. 普通用户不能访问 Wiki 发布结构配置接口。
2. 普通用户只能看到自己可见项目的发布历史和邮件历史。
3. 普通用户不能恢复无权项目的发布历史。
4. 管理员仍然可以查看全部发布历史和邮件历史。
5. Release 页面底部返回链接应使用 `Release_Tool_Config` 中配置的 `main_page`。
6. 发布失败时，发布历史中的 `release_status`、`file_status`、`wiki_status`、`index_status`、`mail_status` 应能指出失败阶段。
7. 未选择附件发布或编辑时，`file_status` 应为 `skipped`，不应被错误标记为 `success`。
8. Redmine 项目文件超过一页时，同名附件检查应覆盖全部文件，而不是只检查第一页。

## 发布状态字段含义

- `pending`：还未执行到该阶段。
- `running`：正在执行该阶段。
- `success`：该阶段已完成。
- `failed`：该阶段失败。
- `skipped`：该阶段本次无需执行，例如未启用邮件或未选择附件。
