# 前端

Vue 3 + TypeScript + Vite + Element Plus。设计说明见 `docs/design/frontend.md`，AI 协作规则见本目录 `AGENTS.md`。

```bash
npm install
npm run dev          # http://localhost:3000，接口请求代理到网关 8000（先 make deps 并启动后端服务）
npm run gen:types    # 后端契约变化后重新生成 src/api/types
npm run lint && npm run typecheck && npm run build
```

目录：

```
src/core/      基础设施（登录、请求、路由合并、布局、权限、公共组件），B 维护
src/modules/   业务模块，与后端服务同名：common / m1-seat / m2-room / m3-repair
src/api/types/ 从 contracts/openapi 生成的类型，不要手改
```
