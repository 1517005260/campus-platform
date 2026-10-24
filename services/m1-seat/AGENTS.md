# M1 自习座位预约（services/m1-seat）

详细设计：`docs/design/m1-seat.md`。需求编号：REQ-M1-xx、INT-01 至 INT-04。

## 本模块的特殊职责

M1 是座位状态的唯一写入方，也是 M2、M3 的被依赖方。`app/api/internal.py` 和 `app/schemas.py` 中 `Internal*` 模型是跨模块契约：修改前先说明对 M2、M3 的影响，只做向后兼容的修改。

## 业务规则

- 预约接口接收 `date + start_hour + end_hour`，用 `campus_common.timeutil.at_hour()` 转成带时区时间再存库；`end_hour` 可以是 24。
- 可调参数（`max_hours`、提醒和自动取消的分钟数）从 `app.rules.load_rules()` 读取（基于 `campus_common.params`），不要写死 4 或 15；接口里的参数读写用 `aload_params` / `asave_params`。
- 座位可约 = 座位和教室 enabled + 在开放时间内 + 无有效预约（booked/checked_in）+ 无未释放且时段重叠的 `room_blocks`（`end_at` 为空视为无限期）。搜索、可用性、创建预约三处使用同一个判断函数，避免规则不一致。
- 院系自习室（`rooms.dept_id` 非空）只对 JWT 中 `dept_id` 相同的用户可见可约。
- 只有 no_show 记违约。用户取消、被 M2/M3 占用而取消都不记。
- 每次座位状态变化写一条 `SeatStatusLog`，带 `source` 和 `ref_id`。

## 并发

- 重叠预约由排除约束 `no_seat_overlap`、`no_user_overlap` 拒绝。捕获 `IntegrityError`，根据约束名返回 409 `SEAT_NOT_AVAILABLE` 或 `USER_TIME_CONFLICT`。
- 创建预约和创建 block 都先 `SELECT ... FROM rooms WHERE id = :id FOR UPDATE`，让同一教室的这两类操作串行执行。
- 状态迁移用带状态条件的更新（`WHERE id = :id AND status = 'booked'`），影响行数为 0 时返回 409 `RESERVATION_STATE_CONFLICT`。

## 跨模块接口的实现要点

`POST /internal/v1/blocks` 用 `campus_common.idempotency.run_idempotent` 包裹；同一事务内完成：插入 block、取消时段内的预约（`cancel_reason` 为 `BLOCKED_BY_M2` / `BLOCKED_BY_M3`）、写状态日志、写 outbox（通知学生、审计、`m1.reservation.cancelled`）。步骤见设计文档第 6 节。

## 定时任务

`app/jobs.py` 的 `mark_no_shows` 是参考实现，函数签名统一为 `fn(session, at)`，在 `app/worker.py` 用 `worker.scan(jobs.xxx, every=60)` 注册。提醒任务照它的结构写：用 `reminded_before_at` / `reminded_late_at` 标记已提醒，条件是"已到时间且未提醒"，这样服务重启后能补发。`send_reminders_before` 要额外要求 `now < start_at`，预约已开始就不再发"即将开始"。

## 测试

- 数据库测试用公共库插件提供的 `db` fixture（每个测试从空的 m1 schema 开始）；时间作为参数传入 `jobs` 函数，不依赖真实时钟。
- 新的定时任务至少覆盖：截止前不处理、截止时刻处理、重复执行不重复处理、其他状态不受影响。
- `pyproject.toml` 的 `[tool.mutmut] source_paths` 列出了做变异测试的文件，新增核心业务文件时加进去。

## 实现进度

`stubs.py` 中的假数据随实现逐个替换。推荐顺序：`internal.py` 的 blocks（M2/M3 等它联调）→ 教室与座位 CRUD → 搜索与可用性 → 预约 → 签到 → 提醒 → 统计。
