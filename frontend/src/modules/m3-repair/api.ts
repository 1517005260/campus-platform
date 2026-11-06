import type { components, paths } from "@/api/types/m3-repair";
import { createApi } from "@/core/http";

export const repairApi = createApi<paths>();

export type WorkOrder = components["schemas"]["WorkOrder"];
export type OrderCreate = components["schemas"]["OrderCreate"];
export type TimelineItem = components["schemas"]["TimelineItem"];
export type RepairSettings = components["schemas"]["RepairSettings"];
export type EscalationRule = components["schemas"]["EscalationRule"];

export const orderStatusLabel: Record<WorkOrder["status"], string> = {
  submitted: "待派单",
  dispatched: "已派单",
  in_progress: "维修中",
  pending_acceptance: "待验收",
  closed: "已关闭",
  cancelled: "已取消",
};

export const timelineActionLabel: Record<TimelineItem["action"], string> = {
  report: "上报",
  cancel: "取消",
  dispatch: "派单",
  start: "开始维修",
  complete: "完工",
  accept: "验收通过",
  admin_accept: "管理员代验收",
  reject: "验收不通过",
  escalate: "超时升级",
};

/** 超时升级通知的对象（按权限码），说明与 common 的 permissions.py 一致 */
export const notifyPermLabel: Record<EscalationRule["notify_perm"], string> = {
  "repair:dispatch": "派单员（repair:dispatch）",
  "repair:manage": "报修管理（repair:manage）",
  "repair:work": "维修工（repair:work）",
};
