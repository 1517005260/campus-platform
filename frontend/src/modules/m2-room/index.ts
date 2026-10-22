import type { AppModule } from "@/core/module";

const m: AppModule = {
  id: "m2-room",
  title: "整教室申请",
  routes: [
    {
      path: "/room/mine",
      component: () => import("./pages/MyApplicationsPage.vue"),
      meta: { title: "我的申请", perms: ["room:apply"] },
    },
    {
      path: "/room/approvals",
      component: () => import("./pages/ApprovalTodoPage.vue"),
      meta: { title: "待我审批", perms: ["room:approve"] },
    },
  ],
  menu: [
    { title: "我的申请", path: "/room/mine", perms: ["room:apply"] },
    { title: "待我审批", path: "/room/approvals", perms: ["room:approve"] },
  ],
};
export default m;
