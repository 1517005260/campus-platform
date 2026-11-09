# M2 整教室预约与审批（services/m2-room）

详细设计：`docs/design/m2-room.md`。需求编号：REQ-M2-xx、INT-02、INT-05。

## 业务规则

- 申请状态：pending → approved / rejected / withdrawn / expired；approved → cancelled。所有状态迁移都走同一个函数，检查当前状态并写 `ApprovalRecord`。
- 提交时把匹配到的审批流复制到 `applications.flow_snapshot`，之后只读快照；修改审批流配置不影响在途申请。
- `scope=dept` 的级别：审批人有 `room:approve` 且 `dept_id` 等于 `applicant_dept_id`；`scope=school`：有 `room:approve_school`。申请人不能审批自己的申请，同一人不能审批同一申请的两级。这些条件只在 `room_service.turn_rules()` 定义一次，审批检查与待办筛选共用。
- 申请人、审批人的显示信息取自登录凭证并保存在申请和审批记录上，读接口不调用 common；通知经 outbox 发给审批人时按权限码（院系级加 `dept_id`）寻址。
- 教室只在最后一级通过时占用（ADR-005）。pending 阶段的驳回、撤回、超时不调用 M1；最终审批请求过占用（`occupy_requested_at` 非空）后未通过就结束的，由 `jobs.release_leftover_blocks` 释放残留占用。
- 参数（违约上限、提前天数）从 `settings` 表读取，默认值是 `schemas.RoomSettings`，读写用 `campus_common.params`。

## 与 M1 的交互

- M2 只调用 M1，不调用 common。只通过 `app/clients.py` 调用，路由里不要直接写 HTTP 请求；`clients.py` 基于 `campus_common.clients`，只写业务语义。M1 的业务错误（如 409 `ROOM_UNDER_MAINTENANCE`）原样返回给前端。
- 最终通过：先记下 `occupy_requested_at` 并提交（与读到同一版本的并发审批、驳回、撤回在此冲突），再 `occupy_room`，成功后在一个事务里改为 approved。本地事务因 `version` 冲突失败时只返回 409，不在请求里释放：对方是成功的最终审批时占用属于它（同一幂等键），对方使申请结束时由 `release_leftover_blocks` 释放。
- 占用请求可能在途时（`room_service.occupy_in_flight()`：`occupy_requested_at` 之后 `RELEASE_GRACE` 内）不能结束 pending 申请：驳回、撤回返回 409 `OCCUPY_IN_PROGRESS`，`expire_overdue` 在 WHERE 中跳过。否则 M1 随后完成占用、取消了学生预约，申请却已结束，被取消的预约不会恢复。
- 取消已通过的申请：先 `release_room`，成功后改为 cancelled；本地提交失败后重试会再次释放（幂等）。
- 开发阶段 `STUB_CLIENTS=true`，客户端返回桩数据；测试中用 `campus_common.testing.record_service_calls()` 记录对 M1 的请求或模拟其返回，用 `monkeypatch` 替换 `clients` 里的业务函数来模拟 M1 失败。测试运行在冻结时钟上（`testing.NOW`）。

## 并发

`Application` 配置了 `version_id_col`，并发修改同一申请时 SQLAlchemy 抛出 `StaleDataError`，转为 409 `APPLICATION_STATE_CONFLICT`。超时扫描用 SKIP LOCKED，与审批人操作冲突时只有一方生效。

## 测试重点

- 多级流转：两级审批依次通过、驳回、非当前级审批人被拒绝、院系不匹配被拒绝、同一人两级被拒绝、截止与开始时刻边界。
- 门槛边界：违约次数等于 `max_violations - 1` 可申请，等于 `max_violations` 不可申请。
- M1 失败时申请状态不变；M1 成功但本地提交失败时不在请求里释放，申请未通过就结束后由 `release_leftover_blocks` 释放（含 `RELEASE_GRACE` 边界、M1 失败后重试、持续失败不挡住其他申请）。
- 超时：截止前不撤销、截止后撤销、重复执行不重复写记录；占用请求在途时驳回、撤回、超时撤销都要等到 `RELEASE_GRACE` 之后。
