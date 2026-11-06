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
      path: "/room/apply",
      component: () => import("./pages/NewApplicationPage.vue"),
      meta: { title: "提交申请", perms: ["room:apply"] },
    },
    {
      // 非数字 id 不匹配，由兜底路由处理
      path: "/room/applications/:id(\\d+)",
      component: () => import("./pages/ApplicationDetailPage.vue"),
      meta: { title: "申请详情", perms: ["room:apply", "room:approve"] },
    },
    {
      path: "/room/approvals",
      component: () => import("./pages/ApprovalTodoPage.vue"),
      meta: { title: "待我审批", perms: ["room:approve"] },
    },
    {
      path: "/room/flows",
      component: () => import("./pages/FlowSettingsPage.vue"),
      meta: { title: "审批流配置", perms: ["room:flow_manage"] },
    },
  ],
  menu: [
    { title: "我的申请", path: "/room/mine", perms: ["room:apply"] },
    { title: "待我审批", path: "/room/approvals", perms: ["room:approve"] },
    { title: "审批流配置", path: "/room/flows", perms: ["room:flow_manage"] },
  ],
};
export default m;
