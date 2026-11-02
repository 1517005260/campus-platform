import type { components, paths } from "@/api/types/m3-repair";
import { createApi } from "@/core/http";

export const repairApi = createApi<paths>();
export type WorkOrder = components["schemas"]["WorkOrder"];

export const orderStatusLabel: Record<WorkOrder["status"], string> = {
  submitted: "待派单",
  dispatched: "已派单",
  in_progress: "维修中",
  pending_acceptance: "待验收",
  closed: "已关闭",
  cancelled: "已取消",
};
