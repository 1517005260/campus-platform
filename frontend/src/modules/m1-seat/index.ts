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
    {
      path: "/seat/availability",
      component: () => import("./pages/RoomAvailabilityPage.vue"),
      meta: { title: "自习室可用性", perms: ["seat:reserve"] },
    },
    {
      path: "/seat/rooms",
      component: () => import("./pages/RoomsAdminPage.vue"),
      meta: { title: "教室与座位管理", perms: ["seat:room_manage"] },
    },
    {
      path: "/seat/checkin",
      component: () => import("./pages/CheckinScreenPage.vue"),
      meta: { title: "签到屏", perms: ["seat:checkin_code"] },
    },
    {
      path: "/seat/stats",
      component: () => import("./pages/SeatStatsPage.vue"),
      meta: { title: "运营统计", perms: ["seat:stats"] },
    },
    {
      path: "/seat/settings",
      component: () => import("./pages/SeatSettingsPage.vue"),
      meta: { title: "系统参数", perms: ["seat:config"] },
    },
  ],
  menu: [
    { title: "搜索座位", path: "/seat/search", perms: ["seat:reserve"] },
    { title: "我的预约", path: "/seat/mine", perms: ["seat:reserve"] },
    { title: "自习室可用性", path: "/seat/availability", perms: ["seat:reserve"] },
    { title: "教室与座位管理", path: "/seat/rooms", perms: ["seat:room_manage"] },
    { title: "签到屏", path: "/seat/checkin", perms: ["seat:checkin_code"] },
    { title: "运营统计", path: "/seat/stats", perms: ["seat:stats"] },
    { title: "系统参数", path: "/seat/settings", perms: ["seat:config"] },
  ],
};
export default m;
