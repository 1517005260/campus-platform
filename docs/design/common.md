# common 公共服务 设计

| 项目 | 内容 |
|---|---|
| 服务 | `services/common`，端口 8004，schema `common` |
| 负责人 | D：登录、用户、角色、权限、院系；F：通知（站内、邮件）、审计、消息消费者 |
| 需求 | REQ-D-01 至 REQ-D-09 |
| 被依赖 | 所有服务依赖它签发的 JWT（只依赖密钥，不依赖服务在线）；M2、M3 调用按权限查用户；所有服务发送通知与审计消息 |

公共库 `libs/campus_common` 也由 D 和 F 维护：D 负责 `auth.py`、`errors.py`，F 负责 `outbox.py`、`inbox.py`、`events.py`、`publisher.py`、`service_client.py`。

## 1. 职责与边界

- **身份与权限**：common 是唯一保存用户和密码的地方。其他服务只看到 JWT 里的 `id/username/name/dept_id/roles/perms`。
- **通知**：其他服务发 `notification.send` 消息，common 负责落库（站内通知）和发送邮件。
- **审计**：其他服务发 `audit.record` 消息，common 负责落库和查询。common 自己的管理操作直接写审计表。

common 不在线时：已登录用户的请求不受影响（各服务本地验 token）；新登录失败；通知与审计消息在 RabbitMQ 中积压（消费者停止时留在原队列，common 数据库不可用时进入延迟重试队列），common 恢复后继续处理。

## 2. 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| `depts` | id, name | |
| `users` | username, password_hash(bcrypt), name, email, dept_id, active | |
| `permissions` | code, module, description | 由 seed 按 `app/permissions.py` 写入 |
| `roles` | code, name, builtin | 预置角色 builtin=true，不可删除 |
| `role_permissions`、`user_roles` | | 多对多 |
| `notifications` | user_id, template, title, content, ref, channels, email_sent_at, read_at | |
| `audit_logs` | at, actor_type, actor_id, module, action, target_type, target_id, before, after, request_id, message_id | 只追加 |
| `inbox` | message_id, type, processed_at | 消费去重 |

## 3. 权限码与预置角色

权限码目录（`app/permissions.py`）：

| 模块 | 权限码 |
|---|---|
| common | `admin:user`、`admin:role`、`audit:read` |
| M1 | `seat:reserve`、`seat:room_manage`、`seat:stats`、`seat:config`、`seat:checkin_code` |
| M2 | `room:apply`、`room:approve`、`room:flow_manage` |
| M3 | `repair:report`、`repair:dispatch`、`repair:work`、`repair:manage` |

预置角色：学生、教师、教室管理员、运营管理员、院系审批人、学校审批人、维修调度员、维修工、签到屏、系统管理员。院系审批人与学校审批人权限相同，区别在用户的 `dept_id` 和 M2 审批流中每一级的 `scope`。

每个环境的种子都会写入引导管理员 `admin`（系统管理员角色，初始密码 `ADMIN_PASSWORD`，默认 `campus123`），新环境部署后用它登录并创建其他用户；已存在时不改动。

新增权限码的流程：在 `permissions.py` 登记 → seed 在下次部署时写入 → 系统管理员把它分配给角色。seed 不修改已存在的角色，避免覆盖线上调整。

## 4. 接口

记法：`方法 路径 (输入) -> 输出 | 权限`。完整契约见 `contracts/openapi/common.json`。

| 接口 | 说明 |
|---|---|
| `POST /api/v1/auth/login (username, password) -> {access_token, expires_in, user}` 无需登录 | 已实现 |
| `GET /api/v1/auth/me () -> CurrentUser` 登录即可 | 已实现 |
| `GET /api/v1/admin/users (keyword?, dept_id?, role?, page, size) -> Page[UserAdmin]` \| `admin:user` | |
| `POST /api/v1/admin/users (UserCreate) -> UserAdmin` \| `admin:user` | |
| `PUT /api/v1/admin/users/{id}/roles (role_codes) -> UserAdmin` \| `admin:user` | |
| `GET /api/v1/admin/roles () -> [RoleOut]` \| `admin:role` | |
| `POST /api/v1/admin/roles (code, name, perms) -> RoleOut` \| `admin:role` | |
| `PATCH /api/v1/admin/roles/{code} (name?, perms?) -> RoleOut` \| `admin:role` | |
| `GET /api/v1/admin/permissions () -> [PermissionOut]` \| `admin:role` | |
| `GET /api/v1/admin/depts () -> [DeptOut]` \| `admin:user` / `room:approve` / `seat:room_manage` | |
| `GET /api/v1/notifications (unread?, page, size) -> Page[NotificationOut]` 登录即可 | 只看自己的 |
| `POST /api/v1/notifications/{id}/read () -> 204` 登录即可 | |
| `GET /api/v1/audit (actor_id?, module?, target_type?, target_id?, date_from?, date_to?, page, size) -> Page[AuditLogOut]` \| `audit:read` | |
| `GET /internal/v1/users/{id} () -> UserContact` 服务间 | 已实现 |
| `GET /internal/v1/users (perm, dept_id?) -> [UserBrief]` 服务间 | 已实现 |

错误码：`LOGIN_FAILED`(401)、`TOKEN_EXPIRED`/`TOKEN_INVALID`/`UNAUTHENTICATED`(401)、`FORBIDDEN`(403)、`UNKNOWN_PERMISSION`(400)、`ROLE_EXISTS`/`USERNAME_EXISTS`(409)、`BUILTIN_ROLE_IMMUTABLE`(409)。

## 5. 消息消费

| 队列 | 绑定 | 处理 |
|---|---|---|
| `common.notification.send` | `campus.events` / `notification.send` | 按 template + params 渲染标题与正文，为每个 user_id 写一条 `notifications` |
| `common.audit.record` | `campus.events` / `audit.record` | 写 `audit_logs`，保留 request_id 与 message_id |

两者都先 `claim_message` 登记 inbox，与业务写入同一事务。队列由公共库 `campus_common.topology` 定义，消费者用 `campus_common.consuming.subscribe()` 注册，失败按错误分类处理（[ADR-010](../adr/010-消息拓扑与失败重试.md)）：

| 失败类型 | 处理 |
|---|---|
| 永久错误：消息不合法、违反约束、处理函数抛 `PermanentError` | 直接进死信队列 `campus.dlq.<队列名>` |
| 临时错误：数据库/网络不可用、超时、处理函数抛 `TransientError` | 进程内快速重试，仍失败转入 `<队列名>.retry.<N>s`，按 5s→30s→2m→10m→30m 延迟后回到原队列，最多 12 次（约 4 小时） |
| 未知错误：其他异常 | 延迟重试 3 次后进死信队列 |

因此 common 的数据库或网络短暂故障时，消息在重试队列中等待，恢复后自动处理，不需要人工介入。死信队列中的消息在修复问题后用 `python -m campus_common.mqctl redrive <队列名>` 放回原队列。处理函数是普通 async 函数（`handle_notification`、`handle_audit`），测试直接调用，不需要 RabbitMQ。

### 通知模板

模板编码由发送方定义，common 维护渲染表。建议放在 `app/templates.py`，形如：

| template | 标题 | 正文参数 |
|---|---|---|
| `seat.remind_before` | 自习预约即将开始 | 教室、座位、开始时间 |
| `seat.remind_late` | 请尽快签到 | 教室、座位、剩余分钟 |
| `seat.no_show_cancelled` | 预约已因未签到取消 | 预约时间、本月违约次数 |
| `seat.cancelled_by_block` | 预约因教室占用/维修被取消 | 原因、预约时间 |
| `room.*`、`repair.*` | 由 M2、M3 提出 | |

未知模板仍然落库（标题用模板编码），并记录警告，避免因模板缺失丢消息。

## 6. 定时任务

| 任务 | 频率 | 逻辑 | 状态 |
|---|---|---|---|
| `send_pending_emails` | 10 秒 | channels 含 email 且 `email_sent_at IS NULL` 的通知，SKIP LOCKED 抢行，查用户邮箱，经 SMTP（开发/测试环境为 Mailpit）发送，成功后写 `email_sent_at`；失败留待下一轮 | 待实现（发信函数 `send_mail()` 已实现） |
| `purge_inbox` | 每天 | 删除 30 天前的 inbox 去重记录（保留期长于延迟重试与死信重放的时间窗口） | 已实现 |

邮件配置：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_SECURITY`（none / starttls / ssl）、`MAIL_FROM`，发送由 `app/mailer.py` 的 `send_mail()` 完成。`SMTP_HOST` 为空表示不发邮件，通知只保留站内信。开发环境指向本机 Mailpit（`localhost:1025`），测试环境指向 Mailpit 容器，生产环境接入真实 SMTP。

## 7. 实现顺序

| 顺序 | 内容 | 负责 |
|---|---|---|
| 1 | 登录、按权限查用户 | 已完成 |
| 2 | 角色与权限管理、用户管理 | D |
| 3 | 通知模板渲染、站内通知查询与已读 | F |
| 4 | 邮件发送任务 | F |
| 5 | 审计查询；common 自身管理操作写审计 | F |

## 8. 待讨论

- 权限变更最长 8 小时后生效（token 有效期）。是否需要更短的有效期或 token 版本号机制？
- 审计记录的保存期限与谁能查看（见伦理记录）。
