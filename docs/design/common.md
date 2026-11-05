# common 公共服务 设计

| 项目 | 内容 |
|---|---|
| 服务 | `services/common`，端口 8004，schema `common` |
| 负责人 | `1517005260`：登录、用户、角色、权限、院系；通知（站内、邮件）、审计、消息消费者 |
| 需求 | REQ-D-01 至 REQ-D-09 |
| 被依赖 | 所有服务依赖它签发的 JWT（只依赖密钥，不依赖服务在线）；M2、M3 调用按权限查用户；所有服务发送通知与审计消息 |

公共库 `libs/campus_common` 也由 `1517005260` 维护，归属决策见 ADR-001。

## 1. 职责与边界

- **身份与权限**：common 是唯一保存用户和密码的地方。其他服务只看到 JWT 里的 `id/username/name/dept_id/roles/perms`。
- **通知**：其他服务发 `notification.send` 消息，common 负责落库（站内通知）和发送邮件。
- **审计**：其他服务发 `audit.record` 消息，common 负责落库和查询。common 自己的管理操作与业务数据在同一事务里直接写审计表（`app/audit.py`）。

common 不在线时：已登录用户的请求不受影响（各服务本地验 token）；新登录失败；通知与审计消息在 RabbitMQ 中积压（消费者停止时留在原队列，common 数据库不可用时进入延迟重试队列），common 恢复后继续处理。

## 2. 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| `depts` | id, name | |
| `users` | username, password_hash(bcrypt), name, email, dept_id, active | |
| `permissions` | code, module, description | 由 seed 按 `app/permissions.py` 写入 |
| `roles` | code, name, builtin | 预置角色 builtin=true，不可删除 |
| `role_permissions`、`user_roles` | | 多对多 |
| `notifications` | user_id, template, title, content, ref, channels, email_sent_at, email_attempts, email_last_error, read_at | email_attempts 只计这封邮件自身的发送失败 |
| `audit_logs` | at, actor_type, actor_id, module, action, target_type, target_id, before, after, request_id, message_id | 只追加 |
| `inbox` | message_id, type, processed_at | 消费去重 |

## 3. 权限码与角色

权限码目录（`app/permissions.py`）：

| 模块 | 权限码 |
|---|---|
| common | `admin:user`、`admin:role`、`audit:read` |
| M1 | `seat:reserve`、`seat:room_manage`、`seat:stats`、`seat:config`、`seat:checkin_code` |
| M2 | `room:apply`、`room:approve`、`room:flow_manage` |
| M3 | `repair:report`、`repair:dispatch`、`repair:work`、`repair:manage` |

预置角色（`builtin=true`）：学生、教师、教室管理员、运营管理员、院系审批人、学校审批人、维修调度员、维修工、签到屏、系统管理员。院系审批人与学校审批人权限相同，区别在用户的 `dept_id` 和 M2 审批流中每一级的 `scope`。

每个环境的种子都会写入引导管理员 `admin`（系统管理员角色，初始密码 `ADMIN_PASSWORD`，默认 `campus123`），新环境部署后用它登录并创建其他用户；已存在时不改动。

新增权限码的流程：在 `permissions.py` 登记 → seed 在下次部署时写入目录 → 系统管理员在"角色与权限"页面把它分配给角色（包括预置角色）。seed 不修改已存在的角色，避免覆盖线上调整。

### 管理规则（`app/rbac.py`）

| 规则 | 原因 | 错误码 |
|---|---|---|
| 角色的权限码必须存在于目录 | 拼错的权限码不会被任何服务识别 | 400 `UNKNOWN_PERMISSION`（`details.unknown`） |
| 预置角色不可删除、不可改名，**权限可以调整** | 文档、演示与其他服务按预置角色的编码和名称说明职责；新增权限码需要分配给预置角色 | 409 `BUILTIN_ROLE_IMMUTABLE` |
| 系统管理员角色 `sys_admin` 必须保留 `admin:user`、`admin:role` | 避免没有人能再管理用户和角色 | 409 `BUILTIN_ROLE_IMMUTABLE` |
| 自定义角色仍有用户时不可删除 | 删除会静默收回这些用户的权限；先调整用户的角色 | 409 `ROLE_IN_USE` |
| 操作者只能经手自己拥有的权限码：分配的角色与被修改用户现有角色的权限；新建角色的权限、修改角色时增加**或移除**的权限、删除角色的权限，都必须是操作者权限的子集 | 只持有 `admin:user` 的账号管理员不能给自己或他人提权、不能重置或降级更高权限的账号；只持有 `admin:role` 的角色管理员不能给角色（包括自己的角色）加上自己没有的权限，也不能拿掉自己没有的权限。改名不涉及权限码，不受此限 | 403 `PERMISSION_ESCALATION`（`details.excess`） |
| 不能停用自己，不能移除自己的 `admin:user` | 避免把唯一的管理员锁在门外 | 409 `SELF_LOCKOUT` |
| 院系只能新建和改名，不能删除 | M1 教室、M2 审批按院系 ID 引用院系，common 无法确认引用已清理；撤销的院系改名标注即可 | 409 `DEPT_EXISTS`（重名） |
| 用户名唯一；院系必须存在；角色必须存在 | | 409 `USERNAME_EXISTS`；400 `DEPT_NOT_FOUND`、`UNKNOWN_ROLE` |

**生效时机**：角色、权限、院系写进 token（ADR-002，HS256，有效期 8 小时，无 refresh token），变更在用户**下次登录**后生效；已签发的 token 到期前仍带旧权限。停用用户立即不能登录，也立即从 `/internal/v1/users` 的结果中消失（M2、M3 不会再把审批或工单派给他），但已登录的会话到期前仍可使用。设置用户角色时给该用户发一条站内通知（`common.roles_changed`），提示重新登录。

**审计**：上述每个写操作在同一事务里经 `audit.record()`（common 中写审计的唯一入口，消息消费者与种子也用它）写一条 `audit_logs`（`actor_type=user`、`module=common`，动作 `user.create`、`user.update`、`user.set_roles`、`role.create`、`role.update`、`role.delete`、`dept.create`、`dept.update`），`before`/`after` 只记录变化的业务字段，重置密码记为 `"password": "reset"`，不记录密码或哈希。

## 4. 接口

记法：`方法 路径 (输入) -> 输出 | 权限`。完整契约见 `contracts/openapi/common.json`，每个接口的错误码写在路由 docstring 中。

| 接口 | 说明 |
|---|---|
| `POST /api/v1/auth/login (username, password) -> {access_token, expires_in, user}` 无需登录 | 停用用户与密码错误同样返回 `LOGIN_FAILED` |
| `GET /api/v1/auth/me () -> CurrentUser` 登录即可 | |
| `GET /api/v1/admin/users (keyword?, dept_id?, role?, active?, page, size) -> Page[UserAdmin]` \| `admin:user` | keyword 匹配用户名或姓名（不区分大小写，`%`、`_` 按字面匹配），按 ID 升序 |
| `POST /api/v1/admin/users (UserCreate) -> UserAdmin` \| `admin:user` | 密码至少 8 位，bcrypt 存储 |
| `PATCH /api/v1/admin/users/{id} (name?, email?, dept_id?, active?, password?) -> UserAdmin` \| `admin:user` | 修改资料、停用/启用、重置密码；`dept_id`/`email` 传 null 表示清空 |
| `PUT /api/v1/admin/users/{id}/roles (role_codes) -> UserAdmin` \| `admin:user` | 整体替换 |
| `GET /api/v1/admin/roles () -> [RoleOut]` \| `admin:role` 或 `admin:user` | 含 `user_count`；预置角色在前 |
| `POST /api/v1/admin/roles (code, name, perms) -> RoleOut` \| `admin:role` | |
| `PATCH /api/v1/admin/roles/{code} (name?, perms?) -> RoleOut` \| `admin:role` | perms 整体替换 |
| `DELETE /api/v1/admin/roles/{code} () -> 204` \| `admin:role` | 只能删除无用户的自定义角色 |
| `GET /api/v1/admin/permissions () -> [PermissionOut]` \| `admin:role` | |
| `GET /api/v1/admin/depts () -> [DeptOut]` \| `admin:user` / `room:approve` / `seat:room_manage` | |
| `POST /api/v1/admin/depts (name) -> DeptOut` \| `admin:user` | |
| `PATCH /api/v1/admin/depts/{id} (name) -> DeptOut` \| `admin:user` | 改名 |
| `GET /api/v1/notifications (unread?, page, size) -> Page[NotificationOut]` 登录即可 | 只看自己的，最新在前 |
| `GET /api/v1/notifications/unread-count () -> {count}` 登录即可 | 顶栏铃铛 |
| `POST /api/v1/notifications/{id}/read () -> 204` 登录即可 | 幂等，保留第一次的已读时间；别人的通知返回 404 |
| `POST /api/v1/notifications/read-all () -> 204` 登录即可 | |
| `GET /api/v1/audit (actor_id?, module?, action?, target_type?, target_id?, date_from?, date_to?, page, size) -> Page[AuditLogOut]` \| `audit:read` | 条件精确匹配；时间为 `[date_from, date_to)`，必须带时区；最新在前 |
| `GET /internal/v1/users/{id} () -> UserContact` 服务间 | |
| `GET /internal/v1/users (perm, dept_id?) -> [UserBrief]` 服务间 | 只返回启用的用户 |

所有接口返回的时间带 `+08:00`（数据库连接时区为业务时区）。

错误码：`LOGIN_FAILED`(401)、`TOKEN_EXPIRED`/`TOKEN_INVALID`/`UNAUTHENTICATED`(401)、`FORBIDDEN`(403)、`PERMISSION_ESCALATION`(403)、`NOT_FOUND`(404)、`UNKNOWN_PERMISSION`/`UNKNOWN_ROLE`/`DEPT_NOT_FOUND`(400)、`USERNAME_EXISTS`/`ROLE_EXISTS`/`DEPT_EXISTS`(409)、`BUILTIN_ROLE_IMMUTABLE`/`ROLE_IN_USE`/`SELF_LOCKOUT`(409)、`VALIDATION_ERROR`(422)。

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

模板编码由发送方定义，渲染表在 `app/templates.py`，站内信与邮件使用同一份标题和正文；时间参数按业务时区显示（如"11月6日 14:00–16:00"）。

| template | 标题 | 使用的参数 |
|---|---|---|
| `seat.remind_before` | 自习预约即将开始 | start_at、end_at |
| `seat.remind_late` | 请尽快签到 | start_at、deadline_minutes |
| `seat.no_show_cancelled` | 预约已因未签到取消 | start_at、end_at |
| `seat.reservation_cancelled_by_block` | 预约因教室占用被取消 | start_at、end_at、block_source、reason |
| `seat.reservation_cancelled_by_admin` | 按 cause 区分：`seat_disabled` 预约因座位停用被取消；`room_disabled` 预约因自习室停用被取消；`room_deregistered` 预约因自习室注销被取消 | start_at、end_at、cause |
| `common.roles_changed` | 你的角色已变更 | roles（common 自己写入，只发站内信） |
| `common.welcome` | 欢迎使用校园资源服务平台 | name（演示数据） |
| `room.*`、`repair.*` | 由 M2、M3 提出后登记 | |

未知模板或缺少参数时仍然落库（标题用模板编码，正文为参数的 JSON），并记录警告，避免因模板缺失丢消息。

## 6. 定时任务

| 任务 | 频率 | 逻辑 |
|---|---|---|
| `send_pending_emails` | 10 秒 | 见下 |
| `purge_inbox` | 每天 03:30 | 删除 30 天前的 inbox 去重记录（保留期长于延迟重试与死信重放的时间窗口） |

`send_pending_emails`（`app/jobs.py`，模式同 M1 的扫描任务）：选取 channels 含 `email`、`email_sent_at IS NULL`、`email_attempts` 小于 3、创建不超过 `EMAIL_MAX_AGE_HOURS`（默认 24）小时的通知，收件人为**启用且有邮箱**的用户，按 (失败次数, ID) 排序（未尝试过的在前，失败过的不会挡住新通知），每轮最多 100 条，`FOR UPDATE SKIP LOCKED` 抢行，经 `mailer.send_mail()` 发送（主题为通知标题，正文为通知内容加系统落款）：

| 情况 | 处理 |
|---|---|
| 发送成功 | 写 `email_sent_at` |
| 这封邮件自身的错误：收件人被拒、内容被拒（`SMTPDataError`）、服务器不支持非 ASCII 地址、地址无法编码等 | `email_attempts` 加一并记录 `email_last_error`，继续发送本轮其他邮件；之后的轮次重试，失败 3 次后不再发送 |
| 服务器层面的错误：连接失败、超时、DNS、断开连接、HELO/认证失败 | 停止本轮，不计入失败次数，下一轮重试 |
| 未配置 SMTP（`SMTP_HOST` 为空） | 不发送，通知只作为站内信 |
| 超过保留期仍未发出 | 不再发送，SMTP 长时间故障恢复后不补发过时的提醒 |
| 邮件已发出、事务提交前进程崩溃 | 下一轮再发一次（至少一次） |

邮件配置：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_SECURITY`（none / starttls / ssl）、`MAIL_FROM`、`EMAIL_MAX_AGE_HOURS`。开发环境指向本机 Mailpit（`localhost:1025`），测试环境指向 Mailpit 容器；本项目只用 Mailpit 验证邮件，不接入真实 SMTP 账号。

## 7. 种子数据（`app/seed.py`）

| 部分 | 内容 | 环境 |
|---|---|---|
| `seed_base` | 权限码目录、预置角色及其权限、引导管理员 `admin`（ID 11） | 所有环境 |
| `seed_demo` | 复旦大学的 8 个院系（ID 1 计算与智能创新学院、2 数学科学学院、3 物理学系、4 经济学院、5 管理学院、6 新闻学院、7 中国语言文学系、8 外国语言文学学院，名称取自复旦大学官网"院系设置"）；自定义角色 `auditor`（审计员：`audit:read`、`seat:stats`）、`user_manager`（账号管理员：`admin:user` 加学生、教师的全部权限码 `seat:reserve`、`room:apply`、`repair:report`。按不越权规则，它能新建、停用、重置学生与教师账号并在两者之间调整角色，不能管理审批人、后勤与管理员账号）；39 个演示账号：ID 1–10 每个预置角色一个（用户名即角色），学生（学号形式的用户名，分布在各院系，其中 1 个已停用）、教师（工号）、院系 2–5 的审批人、第二位教室管理员、维修工、签到屏、两个自定义角色的账号；每个新写入且启用的演示账号一条欢迎通知（只发站内信）；记录这次初始化的审计（`actor_type=system`、`actor_id=seed`） | `SEED_DEMO=true`（默认，所有环境） |

- 全部使用固定 ID 与 `on_conflict_do_nothing`，写完后 `reset_sequences`；角色权限、用户角色、欢迎通知与审计只随新写入的角色或用户一起写入，再次执行不改动任何已存在的数据（`scripts/seed_snapshot.py` 连续执行两次结果相同）。
- ID 1–11 的账号与院系 1、2 被其他服务的演示数据和 `tests/integration` 引用，不能改动它们的 ID 与用户名。
- 演示人员全部虚构；**演示账号的邮箱一律是不可投递的 `<用户名>@campus.local`**，不使用 `fudan.edu.cn` 等真实域名，即使生产环境接入真实 SMTP，提醒也不会发给真实的人（伦理记录 E-05）。

## 8. 实现状态

REQ-D-01 至 REQ-D-09 均已实现，验证方式见 `docs/requirements.md`。

## 9. 待讨论

- 权限变更与停用最长 8 小时后对已登录会话生效（token 有效期）。是否需要更短的有效期或 token 版本号机制（例如 token 带 `ver`，common 停用用户时递增并由各服务缓存校验）？
- 审计记录的保存期限与谁能查看（见伦理记录）。
