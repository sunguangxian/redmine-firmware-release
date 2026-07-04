# Redmine 固件版本发布工具

面向固件团队的 Redmine 发布工具：用户登录 Redmine，选择项目，填写版本信息、变更说明和固件附件，工具自动创建或更新 Redmine 版本、Release Wiki，并按项目 `Release_Tool_Config` 同步版本索引。

当前架构：Vue 3 前端 + FastAPI 后端 + Python 发布逻辑 + SQLite 本地数据存储。

## 启动

```bat
run.bat
```

`run.bat` 会创建 Python 虚拟环境、安装后端依赖；如果本机安装了 npm，会自动安装并构建 Vue 前端，然后启动 FastAPI。

生产模式访问：

```text
http://127.0.0.1:7860
```

开发模式：

```bat
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

- Vue 3 + Element Plus 图形界面。
- FastAPI 后端接口。
- SQLite 保存应用配置、邮件配置、个人账号和联系人模板。
- Redmine 登录支持用户名密码或 API Key。
- 结构管理支持生成、读取、检测、保存项目 `Release_Tool_Config`。
- 版本发布支持版本号、日期、Commit、版本分类、changelog、bin 附件。
- 版本编辑支持读取已有 Release，修改后更新。
- 自动流程包括创建或复用 Redmine 版本、上传项目文件、写 Release Wiki、更新版本信息、同步索引。
- 发布或编辑成功后可发送内网或外网邮件通知。
- 发布或编辑页面会显示后端详细执行日志，便于定位流程执行到哪一步。

## 项目结构规则

项目结构由项目 Wiki 页 `Release_Tool_Config` 决定。

- `single_list`：单列表项目，版本分类可以为空。
- `multi_list`：多分类项目，发布或编辑版本时必须填写版本分类，并且必须匹配配置中的分类。

注意：

- 不会再强制所有项目使用 `5X 常规 / 集群 / record / np500` 等固定分类。
- 只有配置为 `multi_list` 的项目才要求版本分类。
- 未配置多级分类的项目允许版本分类为空。
- 其他项目如果有自己的多级 Wiki 或索引结构，应以该项目的 `Release_Tool_Config` 为准。

single 和 multi 互转：

- 先修改并保存项目 `Release_Tool_Config`。
- 在结构管理页点击“预览重建索引”，确认当前配置会更新哪些页面、哪些 Release 父页面会被调整、哪些 Release 无法归类。
- 确认无误后点击“确认重建索引”，工具会按当前配置全量重建索引。
- 重建索引只更新当前配置涉及的主页面、分类页面、列表页面和 Release 父页面，不会删除旧 Wiki 页面。
- 从 `single_list` 转 `multi_list` 时，历史 Release 如果没有可匹配的分类，预览中会列为“无法归类”，需要先编辑版本分类或调整配置后再重建。

## 旧 Changelog 项目升级

对于旧项目中常见的“一个平台项目包含多个型号，每个型号一个 Changelog 页面”的结构，工具提供通用升级能力，不写死具体项目名。

支持识别的旧结构：

```text
Changelog
├─ Changelog_DM181
├─ Changelog_D705SM
├─ Changelog_for_DM281
└─ DM280
```

旧页面中的版本段支持：

```text
h2. version:V1.0.0.1 (2021-01-01)
## version:V1.0.0.1 (2021-01-01)
```

升级后的目标结构：

```text
Release_Notes
├─ Release_Notes_DM181
│  └─ Release_Notes_DM181_List
└─ Release_DM181_FW_V1_0_0_1
```

规则：

- Redmine 项目 identifier 只作为平台/容器，不再写入 Release 页面名。
- 型号作为分类，例如 `DM181`、`D705SM`。
- Release Wiki 标题格式为 `Release_{model}_FW_{version}`。
- Redmine Version 名称格式为 `{model} {version}`。
- 如果同一型号下存在重复版本号，迁移器会自动追加日期和序号避免覆盖。
- 旧 Wiki 附件会下载后重新上传到项目 Files，并绑定到对应 Redmine Version。
- 新 Release Wiki 页面中的附件表指向项目 Files 下载链接。
- 旧 Changelog 页面和旧 Wiki 附件默认保留，不删除。

升级流程：

1. 在“旧项目升级”页选择项目。
2. 设置入口页，默认 `Changelog`。
3. 点击“预览升级”，查看识别到的型号、历史版本、附件匹配、将创建的 Version、将上传的项目文件和问题列表。
4. 确认无阻塞问题后点击“确认执行升级”。

权限要求：

- 预览需要读取 Wiki、版本和项目文件列表。
- 如果账号无法读取项目 Files，预览会显示警告；当存在旧附件需要迁移时，执行按钮会被禁用。
- 执行需要能够创建/更新 Wiki、创建 Version、下载旧附件、上传项目 Files。

## 邮件配置规则

邮件类型：

- `internal`：内网邮件。
- `external`：外网邮件。

管理员配置：

- 内网 SMTP 服务器、端口、默认发件人、TLS。
- 外网 SMTP 服务器、端口、TLS。
- 管理员全局内网联系人模板。

个人用户配置：

- 个人内网 SMTP 用户名、密码、发件人。
- 个人内网联系人模板：收件人、抄送人。
- 个人外网 SMTP 用户名、密码、发件人。
- 个人外网联系人模板：收件人、抄送人。

发布或编辑时：

- 选择内网邮件时，联系人下拉列表会合并“管理员全局内网联系人模板 + 当前用户个人内网联系人模板”。
- 选择外网邮件时，联系人下拉列表使用当前用户个人外网联系人模板。
- 除了从模板快速选择，也可以手动输入收件人和抄送人。
- 手动输入支持逗号、分号、空格或换行分隔。
- 后端会解析并去重邮箱地址，不再限制收件人必须来自联系人模板。

内网邮件发送使用当前登录用户自己的内网 SMTP 账号密码；不同用户可以维护不同的内网账号密码。

## 发布和编辑日志

版本发布和版本编辑会返回并显示详细日志，包括：

- 开始发布或编辑。
- 变更说明校验。
- 附件读取。
- 读取项目 `Release_Tool_Config`。
- 项目结构识别。
- 分类校验通过或失败。
- 创建或复用 Redmine 版本。
- 创建或编辑 Wiki 页面。
- 附件上传、复用和合并。
- Wiki 写入。
- Redmine 版本信息更新。
- 版本索引同步。
- 邮件通知发送或跳过。
- 刷新版本列表。

如果发布流程失败，接口会尽量返回失败前已执行的日志，前端会显示这些日志帮助定位。

## 数据存储

数据保存到 SQLite：

```text
.redmine-release-tool/release_tool.db
```

主要数据表：

```text
app_settings           # Redmine 地址、登录方式、最近项目等应用配置
mail_servers           # internal / external SMTP 服务器配置
user_internal_email    # 用户个人内网 SMTP 账号配置
user_external_email    # 用户个人外网 SMTP 账号配置
contacts               # 管理员全局联系人和用户个人联系人模板
```

SQLite 并发说明：

- SQLite 同一时间只允许一个写事务。
- 当前代码开启 WAL，并设置 `busy_timeout=30000`、连接 `timeout=30`，多用户同时保存时通常会等待前一个写入完成。
- 极端情况下仍可能遇到 `database is locked`，例如磁盘异常、长时间占用写事务或外部工具锁住数据库。
- 同一用户在两个页面同时保存同一配置时，以最后一次提交为准。

旧版 JSON 配置不再读取：

```text
.redmine-release-tool/settings.json
.redmine-release-tool/users/*.json
```

如需重新配置，启动后在页面中重新保存邮件服务器、联系人和个人账号即可。

## 目录结构

```text
redmine-firmware-release/
├─ frontend/
│  ├─ src/
│  ├─ package.json
│  └─ vite.config.ts
├─ release_tool/
│  ├─ api_app.py
│  ├─ config_store.py
│  ├─ email_sender.py
│  ├─ index_sync.py
│  ├─ legacy_changelog_migrator.py
│  ├─ publisher.py
│  ├─ redmine_api.py
│  ├─ release_page.py
│  ├─ wiki_config.py
│  └─ wiki_templates.py
├─ main.py
├─ requirements.txt
└─ run.bat
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
PUT  /api/mail/user-internal-settings
PUT  /api/mail/user-external-settings
GET  /api/mail/contacts
POST /api/legacy-migration/preview
POST /api/legacy-migration/execute
GET  /api/wiki-config/templates
POST /api/wiki-config/generate
GET  /api/wiki-config/{project_id}/refresh-preview
POST /api/wiki-config/{project_id}/refresh
GET  /api/wiki-config/{project_id}
POST /api/wiki-config/check
PUT  /api/wiki-config/{project_id}
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `RELEASE_TOOL_HOST` | 监听地址，默认 `127.0.0.1`；服务器部署可设为 `0.0.0.0` |
| `RELEASE_TOOL_PORT` | 监听端口，默认 `7860` |
| `REDMINE_BASE_URL` | 工具连接的 Redmine 地址 |
| `RELEASE_TOOL_SAVE_LOGIN_SECRETS` | 默认不在服务器保存 Redmine 登录凭据；设为 `1` 时允许保存 |

## 版本编辑附件规则

- 不选择新附件：保留旧附件。
- 选择新附件且不勾选替换旧附件列表：保留旧附件并追加新附件。
- 选择新附件并勾选替换旧附件列表：Wiki 页面只显示新附件。

替换旧附件列表只修改 Wiki 页面里的附件表，不会删除 Redmine 项目文件里的旧文件。
