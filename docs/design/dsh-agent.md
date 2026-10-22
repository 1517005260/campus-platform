# DSH 自然语言业务代理 设计（附加项 EXT-01）

| 项目 | 内容 |
|---|---|
| 形式 | DeepSeek Harness（DSH）插件，与课程个人 Lab 分析的技术对象相同 |
| 负责人 | F（集成与契约） |
| 计划 | 第 10–11 周（`docs/process.md` 阶段 3）；不影响主线，时间不足时放弃 |
| 需求 | EXT-01 |

## 1. 边界

- 代理只通过网关的公开接口（`/api/v1/...`）调用业务能力，以当前用户的 JWT 作为凭证；不访问任何服务的数据库或 `/internal` 接口，不在代理中重新实现业务规则。
- 接口的含义来自 OpenAPI 契约（`contracts/openapi/*.json`）中的 `summary`、参数描述与错误码；各模块保证这些描述足够让代理理解。

## 2. 覆盖的操作

| 模块 | 操作 | 接口 |
|---|---|---|
| M1 | 查询可用座位、发起预约、查询历史、取消预约 | `GET /api/v1/seat/seats/search`、`POST /api/v1/seat/reservations`、`GET /api/v1/seat/reservations/mine`、`POST .../cancel` |
| M2 | 提交整教室申请、查询申请状态、撤回申请 | `POST /api/v1/room/applications`、`GET .../mine`、`POST .../withdraw` |
| M3 | 上报故障、查询工单状态、取消工单 | `POST /api/v1/repair/orders`、`GET .../mine`、`POST .../cancel` |

## 3. 不确定性处理

意图或必填参数不明确时追问，不擅自执行。例如"我要预约一间教室"：追问日期、时段、楼宇或区域，确认后再提交。写操作在执行前向用户复述将要执行的操作并请求确认。

## 4. 部署

插件的安装、配置（网关地址）与冒烟测试作为部署流水线中的一个步骤（`deploy-test.yml` 集成测试之后），具体机制以 DSH 的插件规范为准，实现时补充到本节。

## 5. 待讨论

- 插件如何安全地持有和刷新用户的 JWT。
- 代理误解意图造成错误操作时的责任与撤销方式（记入 `docs/ethics-log.md`）。
