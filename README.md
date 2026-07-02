# Redmine 固件版本发布

面向固件团队的桌面 Web 工具：用户登录 Redmine、选择项目、填写 Release 信息与固件附件，自动创建/更新 Release Wiki，并从项目 Wiki 自动识别上级页面结构后同步索引。

## 获取

```bash
git clone git@github.com:sunguangxian/redmine-firmware-release.git
cd redmine-firmware-release
run.bat
```

> 仓库地址：https://github.com/sunguangxian/redmine-firmware-release

## 功能

- 图形界面（Gradio，浏览器打开）
- 服务器地址支持用户输入，默认读取上次保存的地址；没有保存时使用当前内网默认地址 `http://192.168.1.208:3000`
- 可通过环境变量 `REDMINE_BASE_URL` 覆盖默认服务器地址
- **记住账号密码**：保存到本地 `%LOCALAPPDATA%\redmine-release-tool\settings.json`
- 多项目：连接后列出所有可访问项目
- 查看已有 Release 列表
- 发布新版本：版本号、日期、Commit、产品线、changelog、`.bin` 附件
- 编辑已有版本（从下拉框加载）
- 编辑已有版本附件：默认保留旧附件；上传新附件时追加；勾选“替换旧附件列表”时只显示新附件
- 自动：创建 Redmine 版本 → 上传项目文件 → 写 Release Wiki → 自动识别 Wiki 结构 → 同步上级页面 / 当前发布列表

## Wiki 结构自动识别

工具不需要为每个项目手写固定配置。发布或刷新索引时会读取当前项目 Wiki：

1. 扫描 `Release_..._FW_...` 版本详情页
2. 查找可能的主页面，例如 `Changelog_for_项目TAG`、`Changelog_for_5X`、`Release_Notes`
3. 判断项目是否已经存在产品线页面，例如：
   - `Release_Notes_Regular`
   - `Release_Notes_Trunking`
   - `Release_Notes_Record`
   - `Release_Notes_NP500`
4. 根据现有结构选择同步模式

### 单列表结构

适合 TP35 这类项目：

```text
Release_Notes
├── Release_TP35_FW_V1_00_00_0030_20260320
├── Release_TP35_FW_V1_0_0_29
└── Release_TP35_FW_V5_3_7_14
```

工具会自动更新 `Release_Notes` 的“版本列表”章节。

### 多产品线结构

适合 DP5X 这类项目：

```text
Changelog_for_5X
├── Release_Notes_Regular
├── Release_Notes_Trunking
├── Release_Notes_Record
└── Release_Notes_NP500
```

工具会自动更新：

- 主页面中的“产品线索引”与各分类 include 区域
- 对应产品线页面中的“版本列表”
- 版本详情页的父页面关系

如果产品线页面本身已经包含 `{{include(...)}}`，工具会优先更新被 include 的列表页；否则直接更新产品线页面的“版本列表”。

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

1. 打开「连接设置」
2. 填写 Redmine 地址（如 `http://192.168.1.208:3000`）、用户名、密码
3. 勾选「记住账号密码」→ 点击「连接 / 保存」
4. 切换到「版本发布」→ 选项目 → 填写表单 → 「发布到 Redmine」

## 凭据文件位置

```text
%LOCALAPPDATA%\redmine-release-tool\settings.json
```

示例：

```json
{
  "base_url": "http://192.168.1.208:3000",
  "username": "zhangsan",
  "password": "your_password",
  "remember": true,
  "last_project": "dp5x"
}
```

> 密码以明文保存在本机，仅适用于内网环境。请勿在公网机器上勾选记住密码。

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
- Redmine 需启用 **REST API** 且允许 HTTP Basic 认证（或使用 API Key 可后续扩展）

## 故障排查

- **登录失败**：确认用户名密码、Redmine 是否允许 API 访问
- **权限不足**：确认用户对目标项目有成员权限
- **上传失败**：确认项目已启用「文件」模块
- **索引页面不符合预期**：优先在目标页面加入 `RELEASE_SYNC_BEGIN` / `RELEASE_SYNC_END` 标记，工具会只更新标记区域
