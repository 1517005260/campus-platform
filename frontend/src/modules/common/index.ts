import type { AppModule } from "@/core/module";

const m: AppModule = {
  id: "common",
  title: "系统管理",
  routes: [
    {
      path: "/admin/users",
      component: () => import("./pages/UsersPage.vue"),
      meta: { title: "用户管理", perms: ["admin:user"] },
    },
    {
      path: "/admin/roles",
      component: () => import("./pages/RolesPage.vue"),
      meta: { title: "角色与权限", perms: ["admin:role"] },
    },
    {
      path: "/admin/depts",
      component: () => import("./pages/DeptsPage.vue"),
      meta: { title: "院系", perms: ["admin:user"] },
    },
    {
      path: "/admin/audit",
      component: () => import("./pages/AuditPage.vue"),
      meta: { title: "操作审计", perms: ["audit:read"] },
    },
    // 所有登录用户可见，入口是顶栏的通知铃铛，不放进"系统管理"菜单
    {
      path: "/notifications",
      component: () => import("./pages/NotificationsPage.vue"),
      meta: { title: "我的通知" },
    },
  ],
  menu: [
    { title: "用户管理", path: "/admin/users", perms: ["admin:user"] },
    { title: "角色与权限", path: "/admin/roles", perms: ["admin:role"] },
    { title: "院系", path: "/admin/depts", perms: ["admin:user"] },
    { title: "操作审计", path: "/admin/audit", perms: ["audit:read"] },
  ],
};
export default m;
