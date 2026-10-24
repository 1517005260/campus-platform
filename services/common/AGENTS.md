# common 公共服务（services/common）

详细设计：`docs/design/common.md`。需求编号：REQ-D-xx。

所有服务都依赖这里签发的 token 和这里定义的权限码，改动的影响面比其他模块大。修改 token 内容、权限码或消息处理时，在 PR 中说明对其他服务的影响。

## 身份与权限

- token 内容由 `campus_common.auth.CurrentUser` 定义，签发用 `create_token`。往 token 里加字段时，其他服务要能容忍旧 token 中没有该字段。
- 权限码只在 `app/permissions.py` 中定义。新增后 seed 会在部署时写入；seed 不改已存在的角色，所以给预置角色加权限要通过管理接口或单独的迁移/种子步骤。
- 密码只存 bcrypt 哈希（`app/security.py`），任何接口和日志都不返回 `password_hash`。
- 预置角色（`builtin=true`）不可删除。

## 通知与审计

- 写入只来自消息（`app/consumers.py`），不提供 HTTP 写接口。消费者用 `campus_common.consuming.subscribe()` 注册，重试与死信由公共库处理；需要明确失败性质时抛 `PermanentError` / `TransientError`。处理函数 `handle_notification`、`handle_audit` 是普通 async 函数，修改后直接在测试里调用验证。
- 每个处理函数第一步 `claim_message` 登记 inbox，业务写入与登记在同一事务内。
- 邮件由 `jobs.send_pending_emails` 扫描发送，消费者只落库。发信函数 `app/mailer.py` 的 `send_mail()` 已实现并有测试；`send_pending_emails` 已注册调度，函数体待实现（REQ-D-06）。这样 SMTP 故障不会阻塞消息消费。`SMTP_HOST` 为空时不发邮件。
- 模板渲染放在 `app/templates.py`（待建）；遇到未知模板仍然落库并记录警告，不让消息进入死信队列。

## 公共库

`libs/campus_common` 由本模块的负责人（D、F）维护，被四个服务使用。改动公共库时同时运行公共库与四个服务的测试；新增公共能力时同步更新根 `AGENTS.md` 的"公共函数优先"表。
