import type { components, paths } from "@/api/types/m2-room";
import { createApi } from "@/core/http";

export const roomApi = createApi<paths>();
export type Application = components["schemas"]["Application"];
export type ApplicationForApprover = components["schemas"]["ApplicationForApprover"];

export const applicationStatusLabel: Record<Application["status"], string> = {
  pending: "审批中",
  approved: "已通过",
  rejected: "已驳回",
  withdrawn: "已撤回",
  expired: "已超时",
  cancelled: "已取消",
};
