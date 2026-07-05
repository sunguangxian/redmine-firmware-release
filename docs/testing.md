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
9. 发布历史接口应返回中文状态标签，例如 `release_status_label`、`status_summary`、`recover_actions`。
10. 登录响应 Cookie 应包含 `HttpOnly`、`Max-Age`、`SameSite`，HTTPS 部署时可通过环境变量启用 `Secure`。

## 发布状态字段含义

- `pending`：还未执行到该阶段。
- `running`：正在执行该阶段。
- `success`：该阶段已完成。
- `failed`：该阶段失败。
- `skipped`：该阶段本次无需执行，例如未启用邮件或未选择附件。

## 发布历史展示字段

发布历史接口除了原始状态字段，还会返回以下便于前端展示的字段：

- `release_status_label`、`file_status_label`、`wiki_status_label`、`index_status_label`、`mail_status_label`：中文状态。
- `status_summary`：把各阶段状态合并成一行摘要。
- `recover_actions`：可执行的恢复动作列表，目前包括 `rebuild_index` 和 `continue`。
- `can_rebuild_index` / `can_continue`：方便旧前端或简单按钮判断。

## 会话 Cookie 配置

- `RELEASE_TOOL_SESSION_TTL_SECONDS`：最长登录时长。
- `RELEASE_TOOL_SESSION_IDLE_SECONDS`：空闲超时时长。
- `RELEASE_TOOL_SESSION_COOKIE_SECURE`：HTTPS 下建议设为 `1`；HTTP 内网访问保持 `0`。
- `RELEASE_TOOL_SESSION_COOKIE_SAMESITE`：默认 `lax`。
