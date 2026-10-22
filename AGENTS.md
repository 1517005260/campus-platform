# AGENTS.md

校园资源服务平台：FastAPI 微服务 monorepo，包含 common、M1 自习座位预约、M2 整教室预约与审批、M3 物业报修工单四个后端服务。整体设计见 `README.md`。

你在某个服务里工作时，先读该服务目录下的 `AGENTS.md` 和 `docs/design/<服务>.md`，它们补充本文件，冲突时以模块文件为准。

## 目录

```
libs/campus_common/     公共库：见下文"公共函数优先"
services/<服务>/app/
  main.py               应用入口（create_app）
  api/                  路由；internal.py 是供其他服务调用的跨模块接口
  schemas.py            请求/响应模型 = 接口契约
  models.py             SQLAlchemy 模型（本服务 schema）
  clients.py            调用其他模块的业务语义函数（M2、M3），通信由 campus_common.clients 完成
  jobs.py, worker.py    定时扫描任务（fn(session, at)）与调度注册（ServiceWorker）
  seed.py               幂等种子数据
  stubs.py              阶段 0 的桩数据，实现接口时逐步替换，最终删除
services/<服务>/migrations/   Alembic 迁移
frontend/src/modules/<id>/  前端模块，与后端服务同名；前端规则见 frontend/AGENTS.md
contracts/              OpenAPI 与消息契约快照（由代码生成）
docs/                   设计、需求、ADR、风险、伦理记录
```

## 命令

```bash
make setup                         # 安装依赖
make deps                          # 启动 Postgres/Redis/RabbitMQ/Mailpit
make run svc=m1-seat               # 运行服务（含迁移和种子）
make test-db                       # 确保测试库 campus_test 存在（可重复执行）
make test svc=m1-seat              # 测试；以本服务的数据库角色连接 campus_test，不会动开发库
make mq-status                     # 消息队列积压、重试、死信、未路由情况
make lint / make fmt               # ruff 检查 / 自动修复
make contracts                     # 改了接口或消息模型后重新生成 contracts/ 和前端类型
make migration svc=m1-seat rev=0002 msg="add seat tags"
```

运行单个测试：`make test svc=m1-seat ARGS="tests/test_jobs.py -k deadline"`（测试只连接 `campus_test`，直接运行 pytest 需先设置 `DATABASE_URL`）。

## 公共函数优先

模块之间的共性能力全部由公共库 `libs/campus_common` 提供，服务里只写业务本身。下表中的事情不要在服务里重新实现；公共库缺少某项能力时，先在 PR 或 issue 里提出加入公共库（D、F 评审），不要在某个模块里先写一份。

| 要做的事 | 用这个 | 服务里写什么 |
|---|---|---|
| 创建应用、错误格式、`/health` `/ready` `/version` | `app_factory.create_app()` | `app/main.py` 只列路由 |
| 数据库模型与会话 | `db.make_metadata(settings.db_schema)`、`db.SessionDep`；`infra_models` 的 `TimestampMixin`、`OutboxMixin`、`InboxMixin`、`IdempotencyKeyMixin`、`ParamMixin` | 本服务的业务表 |
| 迁移 | `migrations.run_migrations()`（`migrations/env.py`）；启动时 `python -m campus_common.migrate` | 迁移脚本 |
| 鉴权 | `auth.require_perm()`、`require_service()`、`CurrentUserDep` | 权限码 |
| 错误、分页、时间 | `errors.AppError`、`errors.not_found()`、`pagination.Page` / `page_params` / `page_of()`、`timeutil.now()/at_hour()` | 错误码 |
| 定时任务 | `worker.ServiceWorker`：`worker.scan(jobs.xxx, every=60)` | `app/jobs.py` 中的 `fn(session, at)` |
| 种子数据 | `seeding.run_seed()`、`reset_sequences()` | `app/seed.py` 中的 `seed_base` / `seed_demo` |
| 可调系统参数 | `infra_models.ParamMixin` + `params.load_params()` / `aload_params()` / `asave_params()` / `seed_params()` | 参数模型（字段与默认值） |
| 调用其他模块 | `clients.m1.M1Client`、`clients.common.CommonClient`、`clients.idempotency_key()` | `app/clients.py` 中的业务语义函数 |
| 发消息 | `outbox.add_event()` + 消息模型 `events.*` | 业务事务里调用 |
| 消费消息 | `consuming.create_broker()`、`subscribe()`、`create_consumer_app()`；`inbox.claim_message()` 去重；`retry.PermanentError/TransientError` | 处理函数 `handle_xxx(envelope)` |
| 服务间写接口幂等（提供方） | `idempotency.run_idempotent()`（同键不同请求返回 409） | 业务动作（不自己提交事务） |
| 测试 | 插件 fixture `client` `migrated` `db` `db_seed`；`testing.user_headers()` `service_headers()` `record_service_calls()` | 本模块的身份 fixture 与测试 |

## 架构约定

这些约定来自已确认的设计决策（见 `docs/adr/`），每条后面是原因。

- **只访问本服务的 schema。** 需要别的模块的数据时，调用对方的 `/internal/v1` 接口或订阅消息。课程要求模块之间不直接访问数据库，数据库角色权限也会拒绝跨 schema 查询。
- **座位状态只由 M1 写。** M2、M3 通过 `POST/DELETE /internal/v1/blocks` 占用和释放教室，并带上 `source` 和 `ref_id`，这样每次状态变化都能追溯到来源。
- **时间一律带时区。** 用 `campus_common.timeutil.now()` 和 `at_hour()`，模型字段用 `DateTime(timezone=True)`，接口字段用 `AwareDatetime`。预约、签到、超时全部依赖时间比较，混入无时区时间会产生 8 小时偏差。ruff 的 DTZ 规则会拦截 `datetime.now()`。
- **按权限码鉴权。** 路由用 `Depends(require_perm("seat:reserve"))`，不要判断角色名，因为管理员可以新建角色。新权限码登记在 `services/common/app/permissions.py`。
- **错误用 `AppError`。** `raise AppError(409, "SEAT_NOT_AVAILABLE", "该时段座位已被预约")`。`code` 是调用方判断的依据，命名用大写下划线，写进路由 docstring。
- **服务间调用写在 `clients.py`。** 用 `campus_common.clients` 中的客户端，`clients.py` 只把业务动作翻译成调用（例如 M2 的"占用教室"）；写操作的幂等键用 `idempotency_key()` 生成，格式 `<模块>-<实体>-<id>-<动作>`（如 `m3-order-7-block`），这样网络重试不会重复执行。`STUB_CLIENTS=true` 时客户端返回桩数据，对方未完成时也能开发。客户端与提供方契约的一致性由公共库的契约测试保证。
- **先调远端，再提交本地。** 需要 M1 配合的状态变更：先调用 M1，成功后才改本地状态并提交；M1 失败时本地保持不变：M1 不可达或拒绝服务间调用时返回 502（`UPSTREAM_UNAVAILABLE` / `UPSTREAM_ERROR`），M1 的业务错误（400/404/409，如 `SEAT_NOT_AVAILABLE`）原样返回（错误转换见 `campus_common.service_client`）。
- **通知和审计发消息。** 在业务事务里调用 `add_event(session, Outbox, "<服务名>", NotificationSend(...))`，与业务数据一起提交。不要直接 HTTP 调用 common 写通知，否则 common 不可用时业务也会失败。
- **消息拓扑与消费只用公共库。** 新增消费队列登记在 `campus_common/topology.py`，消费者用 `campus_common.consuming.subscribe()` 注册，不要在服务里自行声明队列或写重试循环。处理函数需要明确失败性质时抛 `PermanentError`（不重试）或 `TransientError`（延迟重试），见 ADR-010。
- **定时任务扫描数据库。** 参照 `services/m1-seat/app/jobs.py` 的 `mark_no_shows`：`with_for_update(skip_locked=True)` 抢行，状态条件写在 WHERE 里，同一事务内写 outbox。不要用 Celery 的 `countdown`/`eta` 给单条记录挂延时任务，预约被取消或修改后这类任务很难撤销。
- **并发冲突交给数据库。** 能用约束表达的规则（唯一约束、排除约束、`version` 乐观锁）放在数据库里，代码里的预检查只用于给出友好的错误信息。
- **API 层是异步的。** 路由和 `AsyncSession` 用 `async/await`；不要在 async 函数里调用阻塞操作（同步 Session、`requests`、`time.sleep`）。Celery 任务和 seed 用同步 `Session`。
- **Pydantic v2 写法。** `model_validate`、`model_dump`、`field_validator`、`model_validator`；不要用 v1 的 `parse_obj`、`dict()`、`validator`。

## 数据库变更

1. 修改 `models.py`。
2. `make migration ...` 生成迁移，然后逐行检查：autogenerate 会把重命名识别成"删除 + 新增"，也不会生成扩展（如 `btree_gist`）和数据迁移。
3. 迁移"先扩展后收缩"：新列先可空或带默认值，删除旧列放到下一个版本，保证回滚到上一版镜像仍能运行。
4. 种子数据随结构同步更新，保持幂等（`insert ... on_conflict_do_nothing()`）。
5. 本地跑 `alembic upgrade head`、`alembic check`、`alembic downgrade base && alembic upgrade head`。

不要直接在数据库里改结构或数据，所有变更都通过迁移或种子脚本。

## 契约变更

改了 `schemas.py`、路由签名或 `campus_common/events.py` 后运行 `make contracts`，把 `contracts/` 的变化和代码放在同一个提交里，CI 会对比两者。

跨模块接口（`api/internal.py`、消息）只做向后兼容的修改：加可选字段、加新接口。需要删除或改含义时，先在 PR 里说明影响，等调用方确认；CI 检测到破坏性变更时要求 PR 带 `breaking-change-approved` 标签。

## 测试

测试要验证业务行为。合格的测试在实现被改坏时会失败；以下写法通过了也说明不了什么：

- 断言桩数据或常量（例如断言 `stubs.ROOM` 的名字）
- mock 掉被测函数本身，或只断言"被调用过"而不检查参数和结果
- 只覆盖正常路径，不测边界（例如 15 分钟整这一刻是否取消）

写法参考 `services/m1-seat/tests/test_jobs.py`：时间作为参数注入（或用 `time-machine`），覆盖边界前后两侧，验证重复执行不重复计数。需要数据库的测试使用公共库插件提供的 `db` fixture（每个测试从空的服务 schema 开始，需要预置数据时在 `conftest.py` 覆盖 `db_seed`），并标记 `pytestmark = pytest.mark.db`。模拟其他模块用 `record_service_calls()`，不要 mock 被测函数本身。

每写完一个测试，临时改坏对应实现（如把 `<=` 改成 `<`），确认测试失败后再恢复，并在 PR 里写明改了什么。

## 与人协作的方式

- **先给方案再实现。** 对于新功能、跨文件改动或有多种做法的任务，先列出 2 个左右的方案和取舍，等确认后再写代码。简单、明确的小改动可以直接做。
- **一次只做一件事。** 每次改动对应一个需求或 issue，保持在可以逐行审查的规模。
- **需求不清楚时提问。** 设计文档没有覆盖的业务规则，提出问题和你建议的默认做法，不要自行假设后实现。发现文档与代码不一致时指出来。
- **留在任务范围内。** 不修改其他服务的目录、公共库和流水线配置，除非任务明确要求；需要改时说明原因，由人决定。
- **交付时说明验证情况。** 完成后简要报告：改了哪些文件、怎样验证的（运行了哪些测试、改坏了什么来确认测试有效）、还有什么没做或拿不准。

提交和合并由人完成：人审查改动后提交，提交信息格式为 `<类型>(<范围>): <说明> [<需求编号>]`，例如 `feat(m1): 限制单次预约最多 4 小时 [REQ-M1-03]`。合并冲突由人解决。
