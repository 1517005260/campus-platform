# common 公共服务（services/common）

详细设计：`docs/design/common.md`。需求编号：REQ-D-xx。

所有服务都依赖这里签发的 token 和这里定义的权限码，改动的影响面比其他模块大。修改 token 内容、权限码或消息处理时，在 PR 中说明对其他服务的影响。

## 身份与权限

- token 内容由 `campus_common.auth.CurrentUser` 定义，签发用 `create_token`。往 token 里加字段时，其他服务要能容忍旧 token 中没有该字段。
- 权限码只在 `app/permissions.py` 中定义。新增后 seed 会在部署时写入；seed 不改已存在的角色，所以给预置角色加权限要通过管理接口或单独的迁移/种子步骤。
- 密码只存 bcrypt 哈希（`app/security.py`），任何接口和日志都不返回 `password_hash`。
- 用户、角色、院系的管理规则集中在 `app/rbac.py`（预置角色不可删除/改名、`sys_admin` 保留管理权限、不越权、不自锁、院系不删除），每个写操作同一事务写审计（`app/audit.py`）。规则与错误码见设计文档第 3 节，改规则时同步更新。
- 角色与权限的变化在用户下次登录后生效（token 中的权限码在有效期内不变）。

## 通知与审计

- 其他服务的通知与审计只经消息写入（`app/consumers.py`），不提供 HTTP 写接口；common 自身的管理操作在同一事务里直接写审计与站内通知。消费者用 `campus_common.consuming.subscribe()` 注册，重试与死信由公共库处理；需要明确失败性质时抛 `PermanentError` / `TransientError`。处理函数 `handle_notification`、`handle_audit` 是普通 async 函数，修改后直接在测试里调用验证。
- 每个处理函数第一步 `claim_message` 登记 inbox，业务写入与登记在同一事务内。
- 邮件由 `jobs.send_pending_emails` 扫描发送（`app/mailer.py` 的 `send_mail()`），消费者只落库，SMTP 故障不会阻塞消息消费。`SMTP_HOST` 为空时不发邮件。测试用 `tests/conftest.py` 的 `fake_smtp`（替换 `smtplib.SMTP`），不要 mock `send_mail` 或被测任务本身；邮件只用 Mailpit 验证。
- 模板渲染在 `app/templates.py`，新模板（M2、M3 提出的 `room.*`、`repair.*`）登记在 `TEMPLATES` 并补测试；遇到未知模板或缺少参数仍然落库并记录警告，不让消息进入死信队列。

## 种子数据

- `seed_demo` 默认在所有环境执行（`SEED_DEMO=true`）。ID 1–11 的账号与院系 1、2 被其他服务和集成测试引用，不要改。
- 院系用复旦大学官网公布的名称；演示人员虚构；演示账号邮箱只用不可投递的 `@campus.local`。

## 公共库

`libs/campus_common` 由本模块的负责人 `1517005260` 维护，被四个服务使用。改动公共库时同时运行公共库与四个服务的测试；新增公共能力时同步更新根 `AGENTS.md` 的"公共函数优先"表。
