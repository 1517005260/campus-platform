# 前端（frontend/）

Vue 3 + TypeScript + Vite + Element Plus 单页应用。设计见 `docs/design/frontend.md`。根目录 `AGENTS.md` 的协作方式同样适用。

## 目录与职责

```
src/core/        基础设施：http.ts（请求与错误）、auth/（登录与权限）、router.ts、layout/、components/
src/modules/<id>/  业务模块，<id> 与后端服务同名：common / m1-seat / m2-room / m3-repair
    index.ts     模块清单：路由 + 菜单项（含需要的权限码）
    api.ts       本模块的类型化客户端与类型别名
    pages/       页面
src/api/types/   由 npm run gen:types 从 contracts/openapi 生成，不要手改
```

在某个模块里工作时只改该模块目录；需要新公共组件或改 core 时说明原因，由 B 评审。

## 命令

```bash
npm run dev          # 3000 端口，/api 与 /ops 代理到网关 8000
npm run gen:types    # 后端契约更新后重新生成类型
npm run lint && npm run typecheck && npm run build
npm run format       # prettier
```

## 约定

- **接口调用只通过 `createApi<paths>()` 得到的客户端**（见各模块 `api.ts`），路径和参数由契约类型约束。不要手写 `fetch`/`axios` 调接口，否则后端改接口时编译不会报错。唯一例外是 `/ops/*/version`，它不在契约里。
- **错误处理**：接口失败抛 `ApiError`，页面里 `catch (e) { showError(e) }` 统一提示。需要按错误码分支时用 `e.code`（如 `SEAT_NOT_AVAILABLE`），不要比较 message 文本。
- **权限**：页面在路由 `meta.perms` 声明所需权限码，菜单项同样声明；core 负责过滤和拦截。页面内按钮级的权限用 `useAuthStore().can("room:approve")`。
- **时间**：后端返回带时区的 ISO 字符串，显示用 `core/format.ts` 的 `fmtTime`；整点时段用 `HourRangePicker` 组件，提交 `{date, start_hour, end_hour}`。
- **类型**：业务数据类型从 `components["schemas"][...]` 取别名（见 `api.ts`），不要在页面里重新定义一遍接口返回的结构。
- **状态**：登录状态在 `core/auth/store`；模块内部状态优先放在页面组件里，跨页面共享时再建 pinia store 并放在模块目录下。
- **样式**：优先用 Element Plus 组件和它的 CSS 变量，页面只写少量 `scoped` 样式。

## 新增一个页面

1. 在 `src/modules/<id>/pages/` 写页面组件。
2. 在该模块 `index.ts` 的 `routes` 和 `menu` 各加一项，写明 `perms`。
3. 页面里从 `../api` 导入客户端和类型。

## 测试

当前没有前端自动化测试；CI 跑 lint、类型检查、构建、类型与契约一致性。新增页面后在浏览器里用对应角色的演示账号（见根 README）走一遍主要操作。
