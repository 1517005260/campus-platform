# M1 自习座位预约（services/m1-seat）

详细设计：`docs/design/m1-seat.md`。需求编号：REQ-M1-xx、INT-01 至 INT-04。

## 本模块的特殊职责

M1 是座位状态的唯一写入方，也是 M2、M3 的被依赖方。`app/api/internal.py` 和 `app/schemas.py` 中 `Internal*` 模型是跨模块契约：修改前先说明对 M2、M3 的影响，只做向后兼容的修改。

## 业务规则

- 预约接口接收 `date + start_hour + end_hour`，用 `campus_common.timeutil.at_hour()` 转成带时区时间再存库；`end_hour` 可以是 24。
- 可调参数（`max_hours`、提醒和自动取消的分钟数）从 `app.rules.load_rules()` 读取（基于 `campus_common.params`），不要写死 4 或 15；接口里的参数读写用 `aload_params` / `asave_params`。
- 座位可约 = 座位和教室 enabled + 院系允许 + 在开放时间内 + 无有效预约（booked/checked_in）+ 无未释放且时段重叠的 `room_blocks`（`end_at` 为空视为无限期）。规则、时段重叠谓词、取消预约的动作都在 `app/shared.py`，搜索、可用性、创建预约、占用、停用只从这里取，不在别处重写。
- 从带时区的时间取日期或整点先用 `campus_common.timeutil.to_biz()`。
- PATCH 模型（`RoomUpdate`、`SeatUpdate`）的字段写成非 Optional 类型、默认 `None`：没传表示不修改，传 null 由 Pydantic 拒绝（422）；只有本身可空的字段（`dept_id`）写成 `X | None`。
- 读取“当前用户自己的预约”用 `shared.own_reservation()`（他人的预约同样返回 404；状态迁移时 `for_update=True`）。
- 停用座位或教室时取消其尚未结束的有效预约（`ADMIN_DISABLED`，不记违约，通知学生）。
- 院系自习室（`rooms.dept_id` 非空）只对 JWT 中 `dept_id` 相同的用户可见可约。
- 只有 no_show 记违约。用户取消、被 M2/M3 占用而取消、因停用而取消都不记。
- 每次座位状态变化写一条 `SeatStatusLog`，带 `source` 和 `ref_id`。

## 并发

- 重叠预约由排除约束 `no_seat_overlap`、`no_user_overlap` 拒绝，用 `campus_common.db.constraint_errors()` 按约束名返回 409 `SEAT_NOT_AVAILABLE` 或 `USER_TIME_CONFLICT`。
- 创建预约、创建 block、停用座位或教室都先锁教室行（`shared.lock_room()`），让同一教室的这些操作串行执行。
- 同一单号的 block、同一天的签到码由唯一约束保证只有一份（`INSERT ... ON CONFLICT DO NOTHING` 后再读），不用咨询锁。
- 接口里的状态迁移（取消、签到）先 `SELECT ... FROM reservations WHERE id = :id FOR UPDATE` 锁住预约，再检查状态，不允许时返回 409 `RESERVATION_STATE_CONFLICT`；定时扫描把状态条件写在 WHERE 里并用 `SKIP LOCKED`，被锁住的行本轮跳过，所以签到与未签到扫描只有一方生效。

## 跨模块接口的实现要点

`POST /internal/v1/blocks` 用 `campus_common.idempotency.run_idempotent` 包裹；同一事务内完成：插入 block、取消时段内的预约（`cancel_reason` 为 `BLOCKED_BY_M2` / `BLOCKED_BY_M3`）、写状态日志、写 outbox（通知学生、审计、`m1.reservation.cancelled`）。步骤见设计文档第 6 节。

## 定时任务

`app/jobs.py` 的 `mark_no_shows` 是参考实现，函数签名统一为 `fn(session, at)`，在 `app/worker.py` 用 `worker.scan(jobs.xxx, every=60)` 注册。提醒任务照它的结构写：用 `reminded_before_at` / `reminded_late_at` 标记已提醒，条件是"已到时间且未提醒"，这样服务重启后能补发。`send_reminders_before` 要额外要求 `now < start_at`，预约已开始就不再发"即将开始"。

## 测试

- 数据库测试用公共库插件提供的 `db` fixture（每个测试从空的 m1 schema 开始）；时间作为参数传入 `jobs` 函数，不依赖真实时钟。
- 新的定时任务至少覆盖：截止前不处理、截止时刻处理、重复执行不重复处理、其他状态不受影响。
- `pyproject.toml` 的 `[tool.mutmut] source_paths` 列出了做变异测试的文件，新增核心业务文件时加进去。

## 实现进度

M1 业务接口已全部使用真实实现，不再保留阶段 0 的桩数据。
