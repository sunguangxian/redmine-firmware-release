# Redmine 版本发布工具（Python）

面向固件团队的桌面 Web 工具：用户登录 Redmine、选择项目、填写 Release 信息与固件附件，自动创建/更新 Release Wiki 并同步上级 `Release_Notes` 索引。

## 功能

- 图形界面（Gradio，浏览器打开）
- **记住账号密码**：保存到本地 `%LOCALAPPDATA%\redmine-release-tool\settings.json`
- 多项目：连接后列出所有可访问项目
- 查看已有 Release 列表
- 发布新版本：版本号、日期、Commit、产品线、changelog、`.bin` 附件
- 编辑已有版本（从下拉框加载）
- 自动：创建 Redmine 版本 → 上传项目文件 → 写 Release Wiki → 同步 `*_List` / `Release_Notes`

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

```
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
| Trunking / Record | 同上，索引按规则自动分类 |

`{TAG}` 默认取项目 identifier 大写（如 `dp5x` → `DP5X`）。

## 要求

- Redmine 用户需有：项目 Wiki 编辑、版本管理、文件上传权限
- Redmine 需启用 **REST API** 且允许 HTTP Basic 认证（或使用 API Key 可后续扩展）

## 故障排查

- **登录失败**：确认用户名密码、Redmine 是否允许 API 访问
- **权限不足**：确认用户对目标项目有成员权限
- **上传失败**：确认项目已启用「文件」模块
