# 前端 设计

| 项目 | 内容 |
|---|---|
| 目录 | `frontend/`，开发端口 3000，部署为 `campus-frontend` 镜像由网关托管 |
| 负责人 | B 负责 `src/core/` 和 M1 页面；其他模块页面由各模块组负责 |
| 技术栈 | Vue 3、TypeScript、Vite、Element Plus、Pinia、vue-router、openapi-fetch |
| 决策 | [ADR-009](../adr/009-前端框架与模块结构.md) |

## 1. 结构

一个工程，按模块分目录，core 提供基础设施，模块通过"清单"接入：

```
src/
├── core/
│   ├── http.ts            createApi<paths>()：带 token、统一错误、401 处理
│   ├── auth/              登录页、pinia store（token、用户、can(perm)）
│   ├── router.ts          合并各模块路由；登录与权限守卫
│   ├── layout/            侧边菜单（按权限过滤）、顶栏、首页（服务版本）
│   ├── components/        HourRangePicker 等公共组件
│   └── module.ts          AppModule 类型
├── modules/
│   ├── index.ts           模块注册表
│   ├── m1-seat/           index.ts（清单）、api.ts、pages/
│   ├── m2-room/
│   ├── m3-repair/
│   └── common/            系统管理页面
└── api/types/             从 contracts/openapi 生成的类型
```

## 2. 模块清单

```ts
const m: AppModule = {
  id: "m1-seat",
  title: "自习座位",
  routes: [{ path: "/seat/search", component: () => import("./pages/SeatSearchPage.vue"),
             meta: { title: "搜索座位", perms: ["seat:reserve"] } }],
  menu: [{ title: "搜索座位", path: "/seat/search", perms: ["seat:reserve"] }],
};
```

core 把所有模块的 `routes` 挂到带布局的根路由下，`menu` 按当前用户的权限码过滤。页面组件用动态 `import()`，每个页面是独立的构建产物，模块之间没有编译期耦合。

## 3. 接口调用

`openapi-typescript` 从 `contracts/openapi/<服务>.json` 生成 `paths` 和 `components` 类型；`openapi-fetch` 用这些类型约束路径、参数和响应：

```ts
const { data } = await seatApi.GET("/api/v1/seat/seats/search", { params: { query: { date, start_hour, end_hour } } });
```

后端改了接口 → `make contracts` 更新契约与类型 → 前端编译报错指出要改的地方。CI 检查生成的类型与契约一致。

错误：后端统一的 `{code, message, details, request_id}` 转为 `ApiError`，`showError()` 用 Element Plus 提示并附 request_id。401（非登录接口）清除登录状态并跳转登录页。

## 4. 鉴权与权限

- 登录后 token 和用户信息存 localStorage；请求自动带 `Authorization: Bearer`。
- 路由守卫：未登录跳登录页；`meta.perms` 不满足跳首页。
- 菜单、按钮按权限码显示；权限码来自 token 的 `perms`，与后端一致。

## 5. 开发与部署

| 环境 | 方式 |
|---|---|
| 开发 | `npm run dev`，Vite 把 `/api`、`/ops` 代理到网关 8000；后端服务在本机或桩 |
| 部署 | 两阶段镜像：node 构建 → nginx 托管 `dist/`，未知路径回退 `index.html`；外层网关把 `/` 转给它 |

## 6. 已有页面与后续

| 模块 | 已有 | 后续（负责人） |
|---|---|---|
| core | 登录、布局、首页、整点时段组件 | 站内通知铃铛、分页表格组件（B） |
| m1-seat | 搜索座位并预约、我的预约（取消、签到） | 自习室可用性格子图、历史复用、教室管理、签到屏页面、统计（B） |
| m2-room | 我的申请（含资格提示）、待我审批 | 提交申请表单、申请详情与审批记录、审批流配置（C、D） |
| m3-repair | 上报故障、我的报修、工单看板 | 派单、开始/完工、验收评价、工单详情时间线、配置（E、F） |
| common | 角色与权限码查看 | 用户管理、新建角色、审计查询、站内通知列表（D、F） |
