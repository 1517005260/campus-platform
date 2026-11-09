import type { components, paths } from "@/api/types/m2-room";
import { createApi } from "@/core/http";

export const roomApi = createApi<paths>();

export type Application = components["schemas"]["Application"];
export type ApplicationForApprover = components["schemas"]["ApplicationForApprover"];
export type ApplicationCreate = components["schemas"]["ApplicationCreate"];
export type ApprovalFlow = components["schemas"]["ApprovalFlow"];
export type FlowLevel = components["schemas"]["FlowLevel"];
export type RoomSettings = components["schemas"]["RoomSettings"];
export type Eligibility = components["schemas"]["Eligibility"];

export const applicationStatusLabel: Record<Application["status"], string> = {
  pending: "审批中",
  approved: "已通过",
  rejected: "已驳回",
  withdrawn: "已撤回",
  expired: "已超时",
  cancelled: "已取消",
};

export const recordActionLabel: Record<string, string> = {
  approve: "通过",
  reject: "驳回",
  expire: "超时撤销",
  withdraw: "撤回",
  cancel: "取消",
};
