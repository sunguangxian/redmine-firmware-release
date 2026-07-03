# Redmine 固件版本发布

面向固件团队的发布工具：用户登录 Redmine、选择项目、填写 Release 信息与固件附件，自动创建或更新 Release Wiki，并按项目 Wiki 配置页同步索引。

当前架构：Vue 3 前端 + FastAPI 后端 + Python 发布逻辑 + SQLite 数据存储。

## 启动

```bash
run.bat
```

`run.bat` 会创建 Python 虚拟环境、安装后端依赖；如果本机安装了 npm，会自动安装并构建 Vue 前端，然后启动 FastAPI。

生产模式访问：

```text
http://127.0.0.1:7860
```

开发模式：

```bash
python main.py
cd frontend
npm install
npm run dev
```

前端开发访问：

```text
http://127.0.0.1:5173
```

## 功能

- Vue 3 + Element Plus 图形界面
- FastAPI 后端接口
- SQLite 保存配置和用户数据
- Redmine 登录：用户名密码或 API Key
- 结构管理：生成、读取、检测、保存 Release_Tool_Config
- 版本发布：版本号、日期、Commit、产品线、changelog、bin 附件
- 版本编辑：读取已有 Release，修改后更新
- 自动流程：创建或更新 Redmine 版本、上传项目文件、写 Release Wiki、同步索引
- 邮件通知：发布成功或更新成功后可发送邮件
- 邮件配置支持内网和外网隔离

## 邮件配置规则

邮件类型：

- internal：内网邮件
- external：外网邮件

权限规则：

- Redmine 管理员配置内网 SMTP、外网 SMTP、内网联系人。
- 普通用户配置自己的外网 SMTP 用户名、密码、外网发件人、外网联系人。
- 发布时选择内网邮件，只能选择管理员维护的内网联系人。
- 发布时选择外网邮件，只能选择当前用户自己的外网联系人。
- 后端会再次校验联系人范围。

## 数据存储

数据保存到 SQLite：

```text
.redmine-release-tool/release_tool.db
```

主要数据表：

```text
app_settings           # Redmine 地址、登录方式、最近项目等应用配置
mail_servers           # internal / external SMTP 服务器配置
user_external_email    # 用户个人外网 SMTP 账号配置
contacts               # 内网联系人和用户外网联系人
```

当前版本不再读取旧 JSON 配置：

```text
.redmine-release-tool/settings.json
.redmine-release-tool/users/*.json
```

如需重新配置，启动后在页面中重新保存邮件服务器、联系人和个人外网账号即可。

## 目录结构

```text
redmine-firmware-release/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── release_tool/
│   ├── api_app.py
│   ├── config_store.py
│   ├── email_sender.py
│   ├── publisher.py
│   ├── redmine_api.py
│   ├── release_page.py
│   └── wiki_config.py
├── main.py
├── requirements.txt
└── run.bat
```

## API 文档

FastAPI 启动后访问：

```text
http://127.0.0.1:7860/docs
```

主要接口：

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
GET  /api/projects
GET  /api/releases
GET  /api/releases/detail
POST /api/releases/publish
GET  /api/mail/settings
PUT  /api/mail/admin-settings
PUT  /api/mail/user-external-settings
GET  /api/mail/contacts
GET  /api/wiki-config/{project_id}
PUT  /api/wiki-config/{project_id}
```

## 环境变量

| 变量 | 说明 |
|------|------|
| RELEASE_TOOL_HOST | 监听地址，默认 127.0.0.1；服务器部署可设为 0.0.0.0 |
| RELEASE_TOOL_PORT | 监听端口，默认 7860 |
| REDMINE_BASE_URL | 工具连接的 Redmine 地址 |
| RELEASE_TOOL_SAVE_LOGIN_SECRETS | 默认不在服务器保存 Redmine 登录凭据；设为 1 时允许保存 |

## 版本编辑附件规则

- 不选择新附件：保留旧附件。
- 选择新附件，且不勾选替换旧附件列表：保留旧附件并追加新附件。
- 选择新附件，并勾选替换旧附件列表：Wiki 页面只显示新附件。

替换旧附件列表只修改 Wiki 页面里的附件表，不会删除 Redmine 项目文件里的旧文件。
