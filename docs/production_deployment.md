# 生产部署说明

本文档说明如何把 Redmine 固件版本发布工具部署到一台 Windows 服务器，供局域网用户访问。

## 1. 服务器准备

安装以下软件：

- Python 3.8 或更高版本。
- Node.js 18 或更高版本，用于构建 Vue 前端。
- 可选：NSSM，用于注册 Windows 服务。

确认服务器能访问 Redmine，例如：

```powershell
Invoke-WebRequest -UseBasicParsing http://192.168.1.208:3000
```

确认防火墙放行工具端口，默认是 `7860`。

## 2. 拷贝代码

把项目目录复制到服务器，例如：

```text
D:\Tools\redmine-firmware-release
```

如果需要保留当前环境里的邮件配置、联系人模板和用户配置，同时复制：

```text
.redmine-release-tool\release_tool.db
```

如果不复制该目录，服务器首次启动后需要重新配置邮件和联系人。

## 3. 配置生产环境变量

复制配置模板：

```powershell
cd /d D:\Tools\redmine-firmware-release
copy scripts\production.env.example scripts\production.env
```

编辑 `scripts\production.env`：

```text
RELEASE_TOOL_HOST=0.0.0.0
RELEASE_TOOL_PORT=7860
REDMINE_BASE_URL=http://192.168.1.208:3000
RELEASE_TOOL_SAVE_LOGIN_SECRETS=0
RELEASE_TOOL_SESSION_TTL_SECONDS=28800
RELEASE_TOOL_SESSION_IDLE_SECONDS=7200
RELEASE_TOOL_SESSION_COOKIE_SECURE=0
RELEASE_TOOL_SESSION_COOKIE_SAMESITE=lax
```

说明：

- `RELEASE_TOOL_HOST=0.0.0.0` 表示允许局域网访问。
- `RELEASE_TOOL_PORT` 是工具端口。
- `REDMINE_BASE_URL` 是工具连接的 Redmine 地址。
- `RELEASE_TOOL_SAVE_LOGIN_SECRETS=0` 表示不在服务器保存 Redmine 登录密码；确实需要保存时再改为 `1`。
- `RELEASE_TOOL_SESSION_TTL_SECONDS` 是登录会话最长有效时间，默认 8 小时。
- `RELEASE_TOOL_SESSION_IDLE_SECONDS` 是空闲超时时间，默认 2 小时。
- `RELEASE_TOOL_SESSION_COOKIE_SECURE=1` 只适合 HTTPS 访问；纯 HTTP 内网访问时保持 `0`，否则浏览器不会发送 Cookie。
- `RELEASE_TOOL_SESSION_COOKIE_SAMESITE` 默认 `lax`，一般不需要修改。

## 4. 首次安装和构建

执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-production.ps1
```

脚本会执行：

- 创建 `.venv` Python 虚拟环境。
- 安装 `requirements.txt` 中的后端依赖。
- 使用 `npm ci` 安装前端依赖。
- 执行 `npm run build` 生成 `frontend\dist`。

如果服务器不能安装 Node.js，可以在另一台机器先构建好 `frontend\dist`，复制到服务器，然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-production.ps1 -SkipFrontendBuild
```

## 5. 前台启动验证

先用前台方式启动，确认能正常访问：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-production.ps1
```

浏览器访问：

```text
http://服务器IP:7860
```

日志会写入：

```text
logs\release-tool-YYYYMMDD-HHMMSS.log
```

## 6. 注册为 Windows 服务

安装 NSSM 后执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-windows-service.ps1
```

启动服务：

```powershell
nssm start RedmineReleaseTool
```

停止服务：

```powershell
nssm stop RedmineReleaseTool
```

卸载服务：

```powershell
nssm remove RedmineReleaseTool confirm
```

如果 `nssm.exe` 没有加入 `PATH`，指定路径：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-windows-service.ps1 -NssmPath C:\Tools\nssm\nssm.exe
```

## 7. 升级部署

升级时建议：

1. 停止服务。
2. 备份 `.redmine-release-tool\release_tool.db`。
3. 覆盖代码。
4. 重新执行安装脚本。
5. 启动服务并验证登录、项目列表、版本发布预览和邮件配置。

命令示例：

```powershell
nssm stop RedmineReleaseTool
copy .redmine-release-tool\release_tool.db .redmine-release-tool\release_tool.db.bak
powershell -ExecutionPolicy Bypass -File scripts\install-production.ps1
nssm start RedmineReleaseTool
```

## 8. 常见问题

### 页面打不开

检查服务是否启动、端口是否被占用、防火墙是否放行 `7860`。

### 页面能打开但登录失败

检查 `REDMINE_BASE_URL` 是否正确，服务器是否能访问 Redmine。

如果使用 HTTP 访问，确认 `RELEASE_TOOL_SESSION_COOKIE_SECURE=0`；如果设置为 `1`，浏览器只会在 HTTPS 下发送登录 Cookie。

### 登录一段时间后自动退出

检查 `RELEASE_TOOL_SESSION_TTL_SECONDS` 和 `RELEASE_TOOL_SESSION_IDLE_SECONDS`。默认最长 8 小时、空闲 2 小时。

### 邮件发送失败

检查管理员 SMTP 服务器配置、当前用户个人 SMTP 账号密码、发件人地址、收件人地址。

### 前端页面不是最新

重新执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-production.ps1
```

确认 `frontend\dist` 已更新。
