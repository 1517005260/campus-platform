import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/core/auth/store";
import LoginPage from "@/core/auth/LoginPage.vue";
import AppLayout from "@/core/layout/AppLayout.vue";
import HomePage from "@/core/layout/HomePage.vue";
import { modules } from "@/modules";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage, meta: { title: "登录" } },
    {
      path: "/",
      component: AppLayout,
      children: [{ path: "", component: HomePage, meta: { title: "首页" } }, ...modules.flatMap((m) => m.routes)],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.path === "/login") return auth.isLoggedIn ? "/" : true;
  if (!auth.isLoggedIn) return { path: "/login", query: { redirect: to.fullPath } };
  if (to.meta.perms && !auth.can(...to.meta.perms)) return "/";
  document.title = to.meta.title ? `${to.meta.title} · 校园资源服务平台` : "校园资源服务平台";
  return true;
});
