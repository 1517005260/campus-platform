# 需求基线与追踪

维护人：C（组长）。每条需求都要有验收标准、实现位置和验证方式。做不完的需求把状态改为"延后"或"放弃"并写明原因，不要删除。

- **来源**：M1 来自任务书附件 1；M2、M3、D 由各模块组与 AI 交互细化后经组内评审确定；INT 为跨模块集成点。
- **状态**：未开始 / 桩（接口与鉴权就绪，返回假数据）/ 开发中 / 已实现 / 延后 / 放弃
- **验证**：已实现的条目写到具体测试文件或测试名；`单元` = 服务内测试；`DB` = 需要数据库的测试；`契约` = 公共库客户端对照 `contracts/openapi` 的测试；`集成` = `tests/integration` 对部署环境的测试；`演示` = 期末现场演示
- 提交信息和 PR 标题引用编号，例如 `feat(m1): ... [REQ-M1-03]`。

## M1 自习座位预约

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M1-01 | 自习室管理 | 拥有 `seat:room_manage` 的用户可登记、修改、停用自习室，设置楼宇、类型、容量、每周开放时间、所属院系；院系自习室只对本院系用户可见、可约 | `api/rooms.py` | 单元 | 桩 |
| REQ-M1-02 | 座位管理 | 可登记、停用座位；座位在教室内编号唯一；停用的座位不出现在搜索结果中 | `api/rooms.py` | 单元、DB | 桩 |
| REQ-M1-03 | 按整点预约 | 起止均为整点；时长 1 至 `max_hours`（默认 4）小时；必须在开放时间内；违反时返回 400 及对应错误码 | `api/reservations.py` | 单元 | 桩 |
| REQ-M1-04 | 预约冲突 | 同一座位时段重叠的有效预约只能存在一个；同一用户同一时段只能有一个有效预约；并发请求也只有一个成功 | `models.py` 排除约束 | DB：`m1-seat/tests/test_db_constraints.py` | 已实现（约束） |
| REQ-M1-05 | 取消预约 | 开始前可取消，取消后座位立即可被他人预约，不记违约 | `api/reservations.py` | 单元 | 桩 |
| REQ-M1-06 | 签到 | 每间教室每天一个签到码（屏幕显示码与二维码）；在开始前 15 分钟至开始后 `auto_cancel_min` 分钟内输入正确的码签到成功；码错误返回 400 `CHECKIN_CODE_INVALID` | `api/rooms.py`、`api/reservations.py` | 单元 | 桩 |
| REQ-M1-07 | 开始前提醒 | 开始前 `remind_before_min`（默认 15）分钟发送站内通知和邮件，每个预约只发一次 | `jobs.send_reminders_before` | DB | 未开始 |
| REQ-M1-08 | 未签到再提醒 | 开始后 `remind_late_min`（默认 10）分钟仍未签到，再提醒一次 | `jobs.send_reminders_late` | DB | 未开始 |
| REQ-M1-09 | 未签到自动取消并记违约 | 开始后 `auto_cancel_min`（默认 15）分钟仍未签到：状态变为 no_show、释放座位、通知学生、记 1 次违约；重复执行不重复记违约；已签到的不受影响 | `jobs.mark_no_shows` | DB：`m1-seat/tests/test_jobs.py`（截止前后、重复执行、已签到不受影响、可调截止时间）；变异测试 | 已实现 |
| REQ-M1-10 | 搜索座位 | 可按日期时段、楼宇、教室、插座条件搜索；只返回该时段真正可约的座位（未被预约、未被 M2/M3 占用、座位与教室启用、在开放时间内） | `api/rooms.py search_seats` | 单元、DB | 桩 |
| REQ-M1-11 | 历史与再次预约 | 可查看自己的历史预约；可选择一条历史记录，为同一座位预约新的时段（遵守 REQ-M1-03/04） | `api/reservations.py` | 单元 | 桩 |
| REQ-M1-12 | 运营统计 | 拥有 `seat:stats` 的用户可按日期范围、教室查看利用率（已签到小时数 / 开放小时数）、违约率、各小时分布 | `api/admin.py` | 单元 | 桩 |
| REQ-M1-13 | 插座标记 | 座位可标记为无插座、靠近固定插座、靠近移动导轨插座；搜索可按此筛选；座位详情显示标记 | `models.Seat.outlet` | 单元 | 桩 |
| REQ-M1-14 | 系统参数 | 拥有 `seat:config` 的用户可修改 `max_hours`、提醒与自动取消的分钟数，修改后对新预约和下一轮扫描生效 | `api/admin.py`、`rules.py`（`campus_common.params`） | DB：`test_jobs.py::test_respects_configured_deadline`（读取）；写入待实现 | 部分（读取已实现） |
| REQ-M1-15 | 违约记录 | 学生可查看自己的违约记录 | `api/reservations.py` | 单元 | 桩 |

## D 公共层（common 服务）

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-D-01 | 登录 | 用户名密码正确返回 JWT，token 含用户、院系、角色、权限码；错误返回 401 `LOGIN_FAILED`；停用用户不能登录；每个环境都有可登录的引导管理员 `admin` | `api/auth.py` | DB：`common/tests/test_auth.py`（正确登录、密码错误、停用用户）；`test_seed.py`（引导管理员） | 已实现 |
| REQ-D-02 | 角色与权限 | 拥有 `admin:role` 的用户可新建角色、为角色分配权限码；权限码必须存在于目录；预置角色不可删除 | `api/admin.py` | DB | 桩 |
| REQ-D-03 | 用户管理 | 拥有 `admin:user` 的用户可新建用户、停用用户、设置用户角色；变更在用户下次登录后生效 | `api/admin.py` | DB | 桩 |
| REQ-D-04 | 院系 | 维护院系列表；用户归属一个院系（可为空） | `models.Dept` | DB | 部分 |
| REQ-D-05 | 站内通知 | 收到 `notification.send` 消息后为每个用户生成站内通知；同一消息重复投递只生成一次；用户可查看、标记已读 | `consumers.py`、`api/notifications.py` | DB：`common/tests/test_consumers.py::test_duplicate_notification_processed_once` | 部分（消费已实现） |
| REQ-D-06 | 邮件通知 | channels 含 email 的通知通过 SMTP 发送（开发、测试环境发往 Mailpit；未配置 SMTP 时只保留站内信），发送失败下一轮重试 | `jobs.send_pending_emails`、`mailer.py` | 单元：`common/tests/test_mailer.py`（SMTP 连接方式、未配置时关闭） | 部分（发信与配置已实现，扫描任务未开始） |
| REQ-D-07 | 操作审计 | 收到 `audit.record` 后落库，保留 request_id 以关联同一次操作的多个记录 | `consumers.py` | DB：`common/tests/test_consumers.py::test_audit_keeps_request_id` | 已实现 |
| REQ-D-08 | 审计查询 | 拥有 `audit:read` 的用户可按操作人、模块、对象、时间查询审计记录 | `api/notifications.py` | DB | 桩 |
| REQ-D-09 | 按权限查用户 | 其他服务可按权限码（及院系）查询用户，用于查找审批人、维修工 | `api/internal.py` | DB：`common/tests/test_auth.py::test_users_with_perm_filters_by_dept` | 已实现 |

## M2 整教室预约与审批

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M2-01 | 权限门槛 | 拥有 `room:apply` 且近 `violation_window_days`（默认 30）天在 M1 的违约次数小于 `max_violations`（默认 3）才能申请；不满足时说明原因 | `api/applications.py eligibility` | DB：`m2-room/tests/test_api_contract.py`（上限边界、统计窗口、读取调整后的参数） | 部分（违约判断已实现） |
| REQ-M2-02 | 提交申请 | 只能申请 `is_whole_bookable` 的教室；时间在 `advance_days_min`–`advance_days_max` 天之后；与其他 pending/approved 申请时段不重叠；提交后进入第 1 级审批 | `api/applications.py submit` | 单元、DB | 桩 |
| REQ-M2-03 | 审批流配置 | 拥有 `room:flow_manage` 的用户可配置审批流（级数、每级审批范围 dept/school、超时时长）；修改只影响新申请 | `api/approvals.py` | DB | 桩 |
| REQ-M2-04 | 多级审批 | 审批人只能处理当前级别且在其范围内的申请；非最后一级通过进入下一级；最后一级通过后经 M1 占用教室并变为 approved；任一级驳回变为 rejected | `api/approvals.py` | 单元、DB、集成 | 桩 |
| REQ-M2-05 | 超时自动撤销 | 当前级别超过截止时间未处理，自动变为 expired 并通知申请人；与审批同时发生时只有一方生效 | `jobs.expire_overdue` | DB | 未开始 |
| REQ-M2-06 | 撤回与取消 | 审批中可撤回（withdrawn）；已通过、未开始的申请可取消（cancelled）并经 M1 释放教室 | `api/applications.py withdraw` | 单元、集成 | 桩 |
| REQ-M2-07 | 查询 | 申请人可查看自己的申请及每一级审批记录 | `api/applications.py` | 单元 | 桩 |
| REQ-M2-08 | 影响提示 | 审批人在待办中看到批准后将被取消的个人座位预约数 | `api/approvals.py todo` | 单元 | 桩 |
| REQ-M2-09 | 通知 | 提交、每级审批结果、超时、取消时通知相关人 | outbox | DB | 未开始 |

## M3 物业报修工单

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M3-01 | 上报故障 | 拥有 `repair:report` 的用户选择教室（及可选座位）、分类、描述、照片提交工单；教室必须存在于 M1；通知调度员 | `api/orders.py report` | 单元 | 桩 |
| REQ-M3-02 | 取消工单 | 报修人在派单前可取消 | `api/orders.py cancel` | 单元 | 桩 |
| REQ-M3-03 | 派单 | 调度员指定维修工（必须拥有 `repair:work`）、截止时间，并决定维修期间是否下架教室 | `api/work.py dispatch` | 单元、DB | 桩 |
| REQ-M3-04 | 维修中 | 维修工开始维修，状态变为 in_progress；若需下架教室，先经 M1 下架，失败则状态不变 | `api/work.py start` | 单元、集成 | 桩 |
| REQ-M3-05 | 完工 | 维修工提交完工说明，状态变为 pending_acceptance；教室在验收前保持下架；通知报修人 | `api/work.py complete` | 单元 | 桩 |
| REQ-M3-06 | 验收与评价 | 报修人评分 1–5 并验收，工单关闭并经 M1 恢复教室；验收不通过退回 in_progress | `api/orders.py` | 单元、集成 | 桩 |
| REQ-M3-07 | 超时升级 | 工单在 dispatched / in_progress / pending_acceptance 状态停留超过配置时长，升级一级并通知 `repair:manage`；同一超时只升级一次 | `jobs.escalate_overdue` | DB | 未开始 |
| REQ-M3-08 | 代验收 | 报修人超过 `admin_accept_after_hours` 未验收时，`repair:manage` 可代为验收 | `api/orders.py accept` | 单元 | 桩 |
| REQ-M3-09 | 查询与时间线 | 报修人查看自己的工单；调度员与管理员按状态、教室、维修工、是否升级筛选；维修工只看到派给自己的；详情含完整时间线 | `api/orders.py`、`api/work.py` | 单元 | 桩 |
| REQ-M3-10 | 报修配置 | 拥有 `repair:manage` 的用户配置分类与升级规则 | `api/work.py` | 单元 | 桩 |

## 跨模块集成

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| INT-01 | M3 → M1 维修下架 | 需下架的工单进入维修中后，该教室全部座位不出现在搜索结果中、不可预约；验收通过后自动恢复 | M1 `internal.py`、M3 `clients.py`（`campus_common.clients.m1`） | 契约：`libs/campus_common/tests/test_clients_contract.py`；单元：`m3-repair/tests/test_api_contract.py::test_block_and_release_target_same_m1_record`；集成、演示 | 桩（网络调用已通） |
| INT-02 | M2 → M1 整室占用 | 最终审批通过后，教室在申请时段内不接受个人预约；取消后恢复 | M1 `internal.py`、M2 `clients.py`（`campus_common.clients.m1`） | 契约：`libs/campus_common/tests/test_clients_contract.py`；单元：`m2-room/tests/test_api_contract.py::test_occupy_room_uses_stable_idempotency_key`；集成、演示 | 桩（网络调用已通） |
| INT-03 | 写入来源追溯 | 每次座位状态变化记录来源（M1_RESERVATION / M1_ADMIN / M2_OCCUPY / M3_MAINTENANCE）和来源单号，可按座位查询 | M1 `seat_status_logs` | DB、集成 | 部分（表与 no_show 写入） |
| INT-04 | 占用冲突处理 | 占用时段内已有的个人预约自动取消、通知学生、不记违约；接口返回被取消的预约 | M1 `internal.py create_block` | DB、集成 | 桩 |
| INT-05 | 违约影响申请门槛 | 见 REQ-M2-01 | M1 `internal.py`、M2 `clients.py` | 单元 | 部分 |
| INT-06 | 跨模块操作审计 | 每次占用、释放都记审计，包含调用方服务名和 request_id | M1 outbox → common | DB | 未开始 |
| INT-07 | 幂等 | 同一占用请求重复调用（同一幂等键）只生效一次，返回首次结果；同一幂等键对应不同请求内容时返回 409 `IDEMPOTENCY_KEY_REUSED` | `campus_common.idempotency` | DB：`m1-seat/tests/test_idempotency.py`（重复、并发、同键不同请求、失败可重试） | 部分（公共库已实现并测试，M1 接口接入待实现） |

## 非功能需求

| 编号 | 需求 | 验收标准 | 验证 | 状态 |
|---|---|---|---|---|
| NFR-01 | 数据隔离 | 每个服务只能访问自己的 schema，跨 schema 查询被数据库拒绝 | DB：`m1-seat/tests/test_schema_isolation.py`（CI 中各服务以自身角色运行） | 已实现 |
| NFR-02 | 消息可靠 | 业务提交后消息一定发出；路由不到的消息被留存；重复投递只处理一次；临时故障自动延迟重试，永久错误进入死信队列且可重放（ADR-010） | 单元：`libs/campus_common/tests/test_consuming*.py`、`test_retry.py`、`test_topology.py`、`test_outbox.py`；部署环境演练 | 已实现（公共库） |
| NFR-03 | 自动部署 | 合并到 main 后无人工干预部署到测试环境并运行集成测试 | 演示 | 已配置，待服务器 |
| NFR-04 | 发布与回滚 | 生产发布需审批；可回滚到任一历史版本；`/ops/<服务>/version` 显示当前版本 | 演示 | 已配置，待服务器 |
| NFR-05 | 迁移可重放 | 空库一次重放到最新；`alembic check` 无差异；种子幂等（两次执行各表行数不变） | CI：test 任务（重放、`alembic check`、回退重放、种子两次行数比对） | 已实现 |
| NFR-06 | 运维基线 | 各进程有健康检查；按依赖顺序启动；最小权限（数据库角色、消息业务账号、进程级密钥）；非 root 运行；部署前与每日备份（ADR-011） | 部署环境演练 | 已实现，待服务器 |
| NFR-07 | 发布门禁 | 只有通过测试环境集成测试的镜像能发布到生产；版本标签不可修改；部署后校验运行版本与提交 | 演示 | 已配置，待服务器 |
| NFR-08 | 传输加密 | 生产入口使用 HTTPS（TLS 证书、HTTP 跳转、HSTS） | 演示 | 延后：服务器与域名尚未确定，测试阶段经公网 IP 以 HTTP 访问（R-13） |

## 附加项

| 编号 | 需求 | 验收标准 | 状态 |
|---|---|---|---|
| EXT-01 | 自然语言业务代理（设计见 `docs/design/dsh-agent.md`） | 以 DSH 插件形式接入；覆盖 M1 查座位/预约/查历史、M2 申请/查询/撤回、M3 报修/查询/取消；只调用网关公开接口；意图不明确时追问（如"我要预约一间教室"追问时间和区域）；插件安装配置纳入流水线 | 未开始（第 10–11 周） |
