# 测试与基础验证

当前项目先使用 Python 标准库 `unittest` 编写后端核心逻辑测试，避免额外引入测试依赖。前端使用 `vue-tsc` 和 Vite 构建做基础类型检查。

## 运行后端语法检查

```bash
python -m compileall release_tool tests
```

## 运行后端单元测试

```bash
python -m unittest discover -s tests
```

## 运行前端构建检查

```bash
cd frontend
npm ci
npm run build
```

## GitHub Actions

`.github/workflows/backend-tests.yml` 会在 push 到 `main` 或 PR 到 `main` 时自动执行：

- 后端 `compileall`。
- 后端 `unittest`。
- 前端 `npm run build`。

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
11. 版本操作记录页面应显示中文状态，并在可恢复记录上显示“重建索引 / 继续发布”按钮。
12. 默认 `Release_Tool_Config` 模板应生成 `release_detail_mode: inline`。
13. 缺少 `release_detail_mode` 的旧配置应按 `inline` 处理。
14. 内联模式发布后，版本内容应写入 `Release_Notes` 或分类 `list_page`，不应新建单独 Release 页面。
15. 旧 Changelog 迁移默认应生成内联结构；若已有配置显式为 `release_detail_mode: page`，迁移应保留一版本一页模式。
16. 内联模式索引中的 Wiki 链接应指向实际承载页面，不应出现 `INLINE::`。
17. 编辑内联版本并修改版本号时，旧版本块应被删除，新版本块应被写入。
18. 旧 Changelog 迁移中存在重复版本号时，内联块内部标识应唯一，不能互相覆盖。
19. 内联模式发布预览应能正确读取已有版本块附件数量。
20. 内联模式迁移预览应按版本块统计“待写入版本块 / 已有版本块”。
21. 内联模式版本详情页的邮件记录应按版本号过滤，不应混入同一分类页下其他版本的邮件记录。
22. 迁移生成的唯一内联块在后续编辑时应保留唯一块标识，只更新页面显示版本号。
23. 内联模式版本详情页的发布记录也应按版本号过滤，不应混入同一分类页下其他版本的发布记录。
24. 恢复重建索引的提示应使用“Release 记录”，不再写死“一版本一页”的“Release 页面”。

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

## 内联版本模式

`release_detail_mode: inline` 是默认模式。该模式下每个版本用如下标记包住，便于后端定位和编辑：

```text
<!-- RELEASE_INLINE_BEGIN:V1.0.0 -->
## V1.0.0 (2026-07-05)
...
<!-- RELEASE_INLINE_END:V1.0.0 -->
```

常规发布时，内部块标识通常就是版本号。旧 Changelog 迁移时，如果存在同一型号下重复版本号，内部块标识会使用唯一 Release 标题，页面显示版本号仍保持原版本号。

工具内部会用 `INLINE::<页面>::<块标识>` 作为编辑标识；邮件和 Wiki 链接会自动转换为实际承载页面。

## 会话 Cookie 配置

- `RELEASE_TOOL_SESSION_TTL_SECONDS`：最长登录时长。
- `RELEASE_TOOL_SESSION_IDLE_SECONDS`：空闲超时时长。
- `RELEASE_TOOL_SESSION_COOKIE_SECURE`：HTTPS 下建议设为 `1`；HTTP 内网访问保持 `0`。
- `RELEASE_TOOL_SESSION_COOKIE_SAMESITE`：默认 `lax`。
