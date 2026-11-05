# M3 物业报修工单（services/m3-repair）

详细设计：`docs/design/m3-repair.md`。需求编号：REQ-M3-xx、INT-01。

## 业务规则

- 工单状态：submitted → dispatched → in_progress → pending_acceptance → closed；submitted → cancelled；pending_acceptance → in_progress（验收不通过）。所有迁移走 `orders._move()`：检查当前状态、写 `WorkOrderEvent`、刷新 `status_changed_at`。
- 每次状态变化、派单、升级都写一条 `WorkOrderEvent`，时间线完全来自这张表。
- 只有被指派的维修工能开始和完工；只有报修人能取消和验收，管理员在 `admin_accept_after_hours` 后可代验收。
- 没有路由权限码的用户先得到 403；有权限码但看不到该工单（`orders._can_view`）时 404，不暴露工单是否存在；看得到但无权执行该操作时 403。
- 分类和升级规则从 `settings` 表读取，默认值是 `schemas.RepairSettings`，读写用 `campus_common.params`。

## 与 M1 的交互

- `blocks_room=true` 的工单：开始维修时先 `clients.block_room`，成功后才改为 in_progress；关闭时先 `clients.release_room`，成功后才改为 closed。M1 失败时工单状态不变。
- 验收不通过退回 in_progress 时不调用 M1，教室保持下架。
- 幂等键固定为 `m3-order-{id}-block`（`campus_common.clients.idempotency_key()` 生成），不要加时间戳或随机数，否则重试会被当成新请求。请求内容也必须每次相同（M1 同键不同内容返回 409 `IDEMPOTENCY_KEY_REUSED`）：下架起点 `block_start_at` 在首次调用 M1 前写入工单并提交，重试沿用。
- 验收时持有工单行锁调用 `release_room`：M1 中已释放的占用不能再下架，必须保证释放后工单一定关闭。
- 只通过 `app/clients.py`（基于 `campus_common.clients`）调用其他服务；测试中用 `campus_common.testing.record_service_calls()` 记录或模拟 M1 的返回。

## 超时升级

`jobs.escalate_overdue` 按 `escalation_rules` 扫描。计时起点是 `status_changed_at`（进入当前状态）和 `last_escalated_at`（上次升级）中较晚的一个，保证同一段超时只升级一次（因此每个状态只能有一条规则，`RepairSettings` 校验）；到期条件写在 WHERE 里。升级通知按权限码寻址（`NotificationSend.perm`），任务不调用 common。

## 测试重点

- 完整流转：上报 → 派单 → 开始 → 完工 → 验收，检查每一步的状态和时间线。
- 非法操作：非指派维修工开始、派单后取消、代验收时间未到。
- M1 下架失败时工单仍为 dispatched；验收时 M1 释放失败工单仍为 pending_acceptance。
- 升级：未超时不升级、超时升级一次、再过一个周期升级第二次、重复执行不重复升级。
