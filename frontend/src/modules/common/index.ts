import type { AppModule } from "@/core/module";

const m: AppModule = {
  id: "common",
  title: "系统管理",
  routes: [
    {
      path: "/admin/roles",
      component: () => import("./pages/RolesPage.vue"),
      meta: { title: "角色与权限", perms: ["admin:role"] },
    },
  ],
  menu: [{ title: "角色与权限", path: "/admin/roles", perms: ["admin:role"] }],
};
export default m;
