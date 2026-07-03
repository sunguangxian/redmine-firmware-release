# Redmine 固件版本发布

面向固件团队的发布工具：用户登录 Redmine、选择项目、填写 Release 信息与固件附件，自动创建/更新 Release Wiki，并按项目 Wiki 配置页同步索引。

当前开发版已切换为：

```text
Vue 3 前端 + FastAPI 后端 + 原 Python 发布逻辑
```

旧 Gradio 入口仍保留在 `release_tool/app.py`，需要回退时可手动运行：

```bash
python -m release_tool.app
```

## 获取和启动

```bash
git clone git@github.com:sunguangxian/redmine-firmware-release.git
cd redmine-firmware-release
run.bat
```

`run.bat` 会：

1. 创建/启用 Python 虚拟环境
2. 安装 `requirements.txt`
3. 如果本机安装了 `npm`，自动进入 `frontend` 执行 `npm install` 和 `npm run build`
4. 启动 FastAPI 后端
5. 浏览器访问 `http://127.0.0.1:7860`

如果没有安装 Node.js/npm，后端仍会启动，但生产模式下不会显示 Vue 页面。开发时可分别启动：

```bash
# 后端
python main.py

# 前端开发服务器
cd frontend
npm install
npm run dev
```

开发访问：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 代理到：

```text
http://127.0.0.1:7860
```

## 功能

- Vue 3 + Element Plus 图形界面
- FastAPI 后端接口
- Redmine 登录：用户名密码 / API Key
- 多项目选择
- 结构管理：生成、读取、检测、保存 `Release_Tool_Config`
- 版本发布：版本号、日期、Commit、产品线、changelog、`.bin` 附件
- 版本编辑：读取已有 Release，修改后更新
- 自动发布流程：创建/更新 Redmine 版本 → 上传项目文件 → 写 Release Wiki → 同步索引
- 邮件通知：发布成功或更新成功后可发送邮件
- 邮件配置支持内网/外网隔离

## 邮件配置规则

邮件分为两类：

```text
internal = 内网邮件
external = 外网邮件
```

权限规则：

- Redmine 管理员可以配置：
  - 内网 SMTP 服务器
  - 外网 SMTP 服务器
  - 内网联系人
- 普通用户可以配置：
  - 自己的外网 SMTP 用户名
  - 自己的外网 SMTP 密码
  - 自己的外网发件人
  - 自己的外网联系人

发布时：

- 选择“内网邮件”：只能选择管理员维护的内网联系人
- 选择“外网邮件”：只能选择当前用户自己的外网联系人
- 后端会再次校验联系人范围，不能只依赖前端隐藏

配置保存位置：

```text
.redmine-release-tool/settings.json          # 全局配置：邮件服务器、内网联系人等
.redmine-release-tool/users/*.json           # 用户配置：个人外网账号、外网联系人等
```

## 目录结构

```text
redmine-firmware-release/
├── frontend/                    # Vue 3 前端
│   ├── src/
│   │   ├── api/http.ts
│   │   ├── views/
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
│
├── release_tool/
│   ├── api_app.py               # FastAPI 入口
│   ├── app.py                   # 旧 Gradio 入口，保留备用
│   ├── config_store.py          # 配置存储
│   ├── email_sender.py          # 邮件发送
│   ├── publisher.py             # 发布流程编排
│   ├── redmine_api.py           # Redmine API 客户端
│   ├── release_page.py          # Release Wiki 构建/解析
│   └── wiki_config.py           # Wiki 结构配置
│
├── main.py                      # 默认启动 FastAPI
├── requirements.txt
└── run.bat
```

## API 接口

FastAPI 启动后可以访问：

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
| `RELEASE_TOOL_HOST` | 监听地址，默认 `127.0.0.1`；服务器部署可设为 `0.0.0.0` |
| `RELEASE_TOOL_PORT` | 监听端口，默认 `7860` |
| `REDMINE_BASE_URL` | 工具连接的 Redmine 地址 |
| `RELEASE_TOOL_SAVE_LOGIN_SECRETS` | 默认不在服务器保存 Redmine 登录凭据；只有设为 `1` 时才允许服务器端保存 |

## Wiki 结构配置页

每个 Redmine 项目必须创建一个固定 Wiki 页面：

```text
Release_Tool_Config
```

配置必须写在以下标记之间：

```text
<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
```
<!-- RELEASE_CONFIG_END -->
```

工具不再自动猜测 Wiki 结构。发布或刷新索引前会先读取该页面：

```text
存在 Release_Tool_Config 且配置有效
    -> 按配置同步 Release 索引

不存在 Release_Tool_Config
    -> 直接提示异常，不创建版本、不上传附件、不写 Release 页面

配置无效
    -> 直接提示异常，不扫描 Wiki，不猜测结构
```

## 版本编辑附件规则

```text
不选择新附件
    -> 保留旧附件

选择新附件，且不勾选“替换旧附件列表”
    -> 保留旧附件，并追加新附件

选择新附件，并勾选“替换旧附件列表”
    -> Wiki 页面只显示新附件
```

注意：“替换旧附件列表”只修改 Wiki 页面里的附件表，不会删除 Redmine 项目文件里的旧文件。
