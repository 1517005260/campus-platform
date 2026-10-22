import type { AppModule } from "@/core/module";

const m: AppModule = {
  id: "m1-seat",
  title: "自习座位",
  routes: [
    {
      path: "/seat/search",
      component: () => import("./pages/SeatSearchPage.vue"),
      meta: { title: "搜索座位", perms: ["seat:reserve"] },
    },
    {
      path: "/seat/mine",
      component: () => import("./pages/MyReservationsPage.vue"),
      meta: { title: "我的预约", perms: ["seat:reserve"] },
    },
  ],
  menu: [
    { title: "搜索座位", path: "/seat/search", perms: ["seat:reserve"] },
    { title: "我的预约", path: "/seat/mine", perms: ["seat:reserve"] },
  ],
};
export default m;
