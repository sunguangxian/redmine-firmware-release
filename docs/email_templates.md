# 邮件模板

邮件模板在 `release_tool/email_sender.py` 中维护，当前支持两套模板：

- 内网邮件模板：`internal`
- 外网邮件模板：`external`

## 内网邮件模板

内网模板用于公司内部通知，默认包含较完整的信息：

- 项目
- 版本
- 产品线
- 发布日期
- Commit
- 变更说明
- 附件列表
- Release Wiki 链接
- Redmine 项目文件链接

对应函数：

```python
def build_internal_release_email_subject(...):
    ...


def build_internal_release_email_body(...):
    ...
```

## 外网邮件模板

外网模板用于客户或外部联系人通知，默认隐藏内部信息：

- 不显示 Commit
- 不显示 Redmine Wiki 链接
- 不显示 Redmine 项目文件链接

默认包含：

- 项目
- 版本
- 产品线
- 发布日期
- 变更说明
- 附件列表
- 技术支持提示

对应函数：

```python
def build_external_release_email_subject(...):
    ...


def build_external_release_email_body(...):
    ...
```

## 选择规则

版本发布页选择“内网邮件”时，使用内网联系人和内网模板。

版本发布页选择“外网邮件”时，使用当前用户的外网联系人和外网模板。

为了兼容旧调用，如果没有显式传入模板类型，带个人 SMTP 用户名的发送会按外网模板处理。