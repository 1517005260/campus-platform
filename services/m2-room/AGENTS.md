# M2 整教室预约与审批（services/m2-room）

详细设计：`docs/design/m2-room.md`。需求编号：REQ-M2-xx、INT-02、INT-05。

## 业务规则

- 申请状态：pending → approved / rejected / withdrawn / expired；approved → cancelled。所有状态迁移都走同一个函数，检查当前状态并写 `ApprovalRecord`。
- 提交时把匹配到的审批流复制到 `applications.flow_snapshot`，之后只读快照；修改审批流配置不影响在途申请。
- `scope=dept` 的级别：审批人的 `dept_id` 必须等于 `applicant_dept_id`。审批人不能审批自己的申请。
- 教室只在最后一级通过时占用（ADR-005）。pending 阶段的驳回、撤回、超时都不需要调用 M1。
- 参数（违约上限、提前天数）从 `settings` 表读取，默认值是 `schemas.RoomSettings`，读写用 `campus_common.params`。

## 与 M1 的交互

- 只通过 `app/clients.py` 调用 M1 和 common，路由里不要直接写 HTTP 请求；`clients.py` 基于 `campus_common.clients`，只写业务语义。
- 最终通过：先 `occupy_room`，成功后在一个事务里改为 approved。本地事务因 `version` 冲突失败时，重新读取该申请：已是 approved（并发的另一次审批已成功，占用属于它）则不做任何操作并返回 409；否则调用 `release_room` 撤销占用。同一申请的占用使用同一个幂等键，盲目释放会撤掉成功一方的占用。这条补偿路径要有测试（含并发两次审批）。
- 取消已通过的申请：先 `release_room`，成功后改为 cancelled。
- 开发阶段 `STUB_CLIENTS=true`，客户端返回桩数据；测试中用 `campus_common.testing.record_service_calls()` 记录对 M1 的请求或模拟其返回，用 `monkeypatch` 替换 `clients` 里的业务函数来模拟 M1 失败。

## 并发

`Application` 配置了 `version_id_col`，并发修改同一申请时 SQLAlchemy 抛出 `StaleDataError`，转为 409 `APPLICATION_STATE_CONFLICT`。超时扫描用 SKIP LOCKED，与审批人操作冲突时只有一方生效。

## 测试重点

- 多级流转：两级审批依次通过、第一级驳回、非当前级审批人被拒绝、院系不匹配被拒绝。
- 门槛边界：违约次数等于 `max_violations - 1` 可申请，等于 `max_violations` 不可申请。
- M1 失败时申请状态不变；M1 成功但本地提交失败时发生补偿释放。
- 超时：截止前不撤销、截止后撤销、重复执行不重复写记录。
