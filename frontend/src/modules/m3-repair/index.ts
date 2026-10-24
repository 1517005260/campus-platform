import type { AppModule } from "@/core/module";

const m: AppModule = {
  id: "m3-repair",
  title: "物业报修",
  routes: [
    {
      path: "/repair/mine",
      component: () => import("./pages/MyOrdersPage.vue"),
      meta: { title: "我的报修", perms: ["repair:report"] },
    },
    {
      path: "/repair/orders",
      component: () => import("./pages/OrderBoardPage.vue"),
      meta: { title: "工单看板", perms: ["repair:dispatch", "repair:work", "repair:manage"] },
    },
  ],
  menu: [
    { title: "我的报修", path: "/repair/mine", perms: ["repair:report"] },
    { title: "工单看板", path: "/repair/orders", perms: ["repair:dispatch", "repair:work", "repair:manage"] },
  ],
};
export default m;
