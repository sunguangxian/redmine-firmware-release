# Redmine 固件版本发布

面向固件团队的桌面 Web 工具：用户登录 Redmine、选择项目、填写 Release 信息与固件附件，自动创建/更新 Release Wiki，并按项目 Wiki 配置页同步索引。

## 获取

```bash
git clone git@github.com:sunguangxian/redmine-firmware-release.git
cd redmine-firmware-release
run.bat
```

> 仓库地址：https://github.com/sunguangxian/redmine-firmware-release

## 功能

- 图形界面（Gradio，浏览器打开）
- Redmine 地址由工具服务器统一配置；可通过环境变量 `REDMINE_BASE_URL` 覆盖默认地址
- 支持两种 Redmine 登录方式：用户名密码、API Key
- 多人使用：每个浏览器会话独立保存当前 Redmine 登录状态，互不共享
- 登录首页可勾选“在本机浏览器记住账号密码”，凭据只保存到当前浏览器
- 邮件配置、常用收件人/抄送按 Redmine 用户保存到工具服务器，同一用户换电脑登录后可同步
- 服务器默认不保存 Redmine 密码/API Key；如确需服务器端个人模式保存，启动前设置 `RELEASE_TOOL_SAVE_LOGIN_SECRETS=1`
- 多项目：连接后列出所有可访问项目
- 管理员结构管理：在工具中生成、读取、检测、保存每个项目的 `Release_Tool_Config`
- 查看已有 Release 列表
- 发布新版本：版本号、日期、Commit、产品线、changelog、`.bin` 附件
- 编辑已有版本（从下拉框加载）
- 编辑已有版本附件：默认保留旧附件；上传新附件时追加；勾选“替换旧附件列表”时只显示新附件
- 可选发布邮件：保存常用收件人/抄送后，发布时选择联系人；本次选择的固件文件会作为邮件附件
- 自动：创建 Redmine 版本 → 上传项目文件 → 写 Release Wiki → 读取 `Release_Tool_Config` → 同步上级页面 / 当前发布列表

## 登录方式

### 用户名密码

在登录首页选择“用户名密码”，填写用户名、密码后登录。

### API Key

在登录首页选择“API Key”，填写 API Key 后登录。工具会通过请求头：

```text
X-Redmine-API-Key: <your api key>
```

访问 Redmine REST API。

API Key 方式适合管理员给发布工具单独授权，也避免用户在工具里保存 Redmine 密码。

登录首页的“在本机浏览器记住账号密码”会把登录方式、用户名密码或 API Key 保存到当前浏览器的 `localStorage`。这些信息不会写入服务器工作区，不会被其他电脑或其他浏览器共享。

邮件配置、SMTP 账号、常用收件人和抄送属于个人设置。用户登录 Redmine 后，工具会按 Redmine 登录名把这些设置保存到服务器工作区：

```text
项目工作区\.redmine-release-tool\users\
```

因此同一个用户从不同电脑访问同一台工具服务器并登录后，可以同步自己的邮件和联系人设置。部署时需要持久化 `.redmine-release-tool` 目录；如果换服务器或清空该目录，个人设置不会自动同步过去。

## 服务器部署

工具可以部署到内网服务器供开发人员使用。推荐使用 API Key 登录，并在反向代理、VPN 或 Gradio 访问密码后面运行。

```powershell
$env:RELEASE_TOOL_HOST="0.0.0.0"
$env:RELEASE_TOOL_PORT="7860"
$env:RELEASE_TOOL_AUTH="release:change-this-password"
python -m release_tool.app
```

环境变量：

| 变量 | 说明 |
|------|------|
| `RELEASE_TOOL_HOST` | 监听地址，默认 `127.0.0.1`；服务器部署可设为 `0.0.0.0` |
| `RELEASE_TOOL_PORT` | 监听端口，默认 `7860` |
| `RELEASE_TOOL_AUTH` | 可选的 Gradio 访问密码，格式 `用户名:密码` |
| `REDMINE_BASE_URL` | 工具连接的 Redmine 地址 |
| `RELEASE_TOOL_SAVE_LOGIN_SECRETS` | 默认不在服务器保存 Redmine 登录凭据；只有设为 `1` 时才允许服务器端保存 |

多人部署时不要设置 `RELEASE_TOOL_SAVE_LOGIN_SECRETS=1`。服务器上的 `.redmine-release-tool\settings.json` 只保存共享默认配置；个人邮件和联系人设置保存到 `.redmine-release-tool\users\`。

## 管理员结构管理

管理员可以在工具的「结构管理」页维护每个项目的 Wiki 结构：

1. 先在登录首页登录 Redmine
2. 打开「结构管理」
3. 选择项目
4. 选择结构模板
5. 点击“生成模板”
6. 检查或修改配置内容
7. 点击“检测配置”
8. 点击“保存到项目 Wiki”

保存后，工具会把内容写入当前项目的 Wiki 页面：

```text
Release_Tool_Config
```

如果当前用户没有 Wiki 编辑权限，保存会失败并显示 Redmine 权限错误。

## Wiki 结构配置页

每个 Redmine 项目必须创建一个固定 Wiki 页面：

```text
Release_Tool_Config
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

配置必须写在以下标记之间：

```text
<!-- RELEASE_CONFIG_BEGIN -->
```yaml
mode: single_list
main_page: Release_Notes
```
<!-- RELEASE_CONFIG_END -->
```

### 模板文件

仓库已提供三种模板，可直接复制到项目 Wiki 的 `Release_Tool_Config` 页面，也可以通过工具「结构管理」页生成：

| 结构 | 模板文件 | 适用场景 |
|------|----------|----------|
| 单列表 | `docs/wiki_templates/Release_Tool_Config_single_list.md` | TP35 这类只有一个 Release 分类，主页面直接显示完整版本列表的项目 |
| 多分类 include | `docs/wiki_templates/Release_Tool_Config_multi_list_include.md` | DP5X 这类主页面显示最近版本，分类页面 + 独立 List 页面显示完整列表的结构 |
| 多分类直接列表 | `docs/wiki_templates/Release_Tool_Config_multi_list_direct.md` | 主页面 + 分类页面，但不额外拆 `xxx_List` 页面 |

### 单列表结构

适合 TP35 这类项目：

```text
Release_Notes
├── Release_TP35_FW_V1_00_00_0030_20260320
├── Release_TP35_FW_V1_0_0_29
└── Release_TP35_FW_V5_3_7_14
```

配置示例：

```yaml
mode: single_list
main_page: Release_Notes
release_page_prefix: Release_TP35_FW_
```

工具会自动维护 `Release_Notes` 的完整版本列表。

### 多分类 include 结构

适合 DP5X 这类项目：

```text
Changelog_for_5X
└── {{include(Release_Notes)}}

Release_Notes
├── Release_Notes_Regular -> {{include(Release_Notes_Regular_List)}}
├── Release_Notes_Trunking -> {{include(Release_Notes_Trunking_List)}}
├── Release_Notes_Record -> {{include(Release_Notes_Record_List)}}
└── Release_Notes_NP500 -> {{include(Release_Notes_NP500_List)}}
```

配置示例：

```yaml
mode: multi_list
main_page: Release_Notes
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular_List

  - key: Trunking
    title: Trunking 集群
    hub_page: Release_Notes_Trunking
    list_page: Release_Notes_Trunking_List

  - key: Record
    title: Record 录音
    hub_page: Release_Notes_Record
    list_page: Release_Notes_Record_List

  - key: NP500
    title: NP500
    hub_page: Release_Notes_NP500
    list_page: Release_Notes_NP500_List
```

工具会自动生成固定结构：`Release_Notes` 只显示分类入口和每类最近版本，分类页显示完整列表；`Changelog_for_5X` 可作为旧入口，仅 include `Release_Notes`。

### 多分类直接列表结构

如果不想建立独立 `xxx_List` 页面，可以把 `list_page` 设置成和 `hub_page` 一样：

```yaml
mode: multi_list
main_page: Release_Notes
categories:
  - key: Regular
    title: 常规版本 (5X)
    hub_page: Release_Notes_Regular
    list_page: Release_Notes_Regular
```

## 编辑已发布版本

在“编辑已有版本”下拉框中选择版本后，工具会自动加载：

- 版本号
- 发布日期
- Commit
- 产品线
- 变更说明
- 已有附件列表

附件处理规则：

```text
不选择新附件
    -> 保留旧附件

选择新附件，且不勾选“替换旧附件列表”
    -> 保留旧附件，并追加新附件

选择新附件，并勾选“替换旧附件列表”
    -> Wiki 页面只显示新附件
```

注意：“替换旧附件列表”只修改 Wiki 页面里的附件表，不会删除 Redmine 项目文件里的旧文件。

## 发布邮件

工具支持发布成功后发送邮件通知：

1. 登录后在“邮件设置”中填写 SMTP 服务器、端口、发件人、常用收件人、常用抄送并保存
2. 在“版本发布”页勾选“发布成功后发送邮件”
3. 从已保存的联系人里选择收件人和抄送
4. 点击“发布到 Redmine”

邮件内容会包含：

- 项目、版本、产品线、发布日期、Commit
- 变更说明
- Release Wiki 链接
- 项目文件链接
- 本次选择的 `.bin` 文件附件

说明：联系人和邮件配置按当前 Redmine 用户保存；需要新增联系人时，到“邮件设置”里输入并保存后再选择。

## 推荐的自动同步标记

如果想明确指定工具可改写的区域，可以在 Wiki 页面中加入：

```text
<!-- RELEASE_SYNC_BEGIN -->
这里由工具自动生成
<!-- RELEASE_SYNC_END -->
```

有标记时，工具只替换标记之间的内容；没有标记时，会尽量只替换“版本列表”或“产品线索引”章节。

## 分发给用户

1. 将整个 `redmine-release-tool` 文件夹打包 zip 发给用户
2. 用户需安装 **Python 3.10+**
3. 双击 `run.bat`（首次会自动创建虚拟环境并安装依赖）
4. 浏览器打开 `http://127.0.0.1:7860`

## 首次使用

1. 打开工具，连接 Redmine。可选用户名密码或 API Key
2. 打开「结构管理」页，选择项目，生成并保存 `Release_Tool_Config`
3. 打开「邮件设置」配置 SMTP 和常用联系人（需要发邮件时）
4. 切换到「版本发布」→ 选项目 → 填写表单 → 「发布到 Redmine」

## 服务器配置目录

```text
项目工作区\.redmine-release-tool\
```

共享配置文件：

```json
{
  "base_url": "http://192.168.1.208:3000",
  "auth_mode": "api_key",
  "remember": false
}
```

个人邮件配置和联系人保存到：

```text
项目工作区\.redmine-release-tool\users\
```

登录账号密码/API Key 默认不写入服务器配置文件，只保存在用户自己的浏览器 `localStorage`。

## 命令行启动

```bash
cd redmine-release-tool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 产品线

| 选项 | Wiki 命名 |
|------|-----------|
| 常规版本 (5X) | `Release_{TAG}_FW_V5_3_8_3` |
| NP500 | `Release_{TAG}_NP500_FW_V5_3_8_3` |
| Trunking / Record | 同普通 FW 命名，索引按产品线字段或版本规则自动分类 |

`{TAG}` 默认取项目 identifier 大写（如 `dp5x` → `DP5X`）。

## 要求

- Redmine 用户需有：项目 Wiki 编辑、版本管理、文件上传权限
- Redmine 需启用 **REST API**
- 每个项目必须有有效的 `Release_Tool_Config` Wiki 页面
- 发送邮件需要可访问的 SMTP 服务

## 故障排查

- **登录失败**：确认用户名密码或 API Key、Redmine 是否允许 API 访问
- **权限不足**：确认用户或 API Key 对目标项目有成员权限
- **上传失败**：确认项目已启用「文件」模块
- **缺少 Release_Tool_Config**：在「结构管理」页生成并保存项目 Wiki 配置页
- **配置页无效**：检查 `RELEASE_CONFIG_BEGIN` / `RELEASE_CONFIG_END` 中的 `mode`、`main_page`、`categories`
- **邮件发送失败**：确认 SMTP 地址、端口、账号、发件人和网络是否可用
- **索引页面不符合预期**：优先在目标页面加入 `RELEASE_SYNC_BEGIN` / `RELEASE_SYNC_END` 标记，工具会只更新标记区域
