import type { components, paths } from "@/api/types/m3-repair";
import type { paths as SeatPaths } from "@/api/types/m1-seat";
import { createApi } from "@/core/http";

export const repairApi = createApi<paths>();
/** 上报时选教室用 M1 的教室列表（只读调用）。 */
export const seatRoomsApi = createApi<SeatPaths>();

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

export const timelineActionLabel: Record<string, string> = {
  submit: "上报",
  dispatch: "派单",
  start: "开始维修",
  complete: "完工",
  accept: "验收通过",
  reject_acceptance: "验收不通过",
  cancel: "取消",
  escalate: "超时升级",
  admin_accept: "管理员代验收",
};
