import type { components, paths } from "@/api/types/m2-room";
import type { paths as SeatPaths } from "@/api/types/m1-seat";
import { createApi } from "@/core/http";

export const roomApi = createApi<paths>();
/**
 * 选教室用 M1 的教室列表（is_whole_bookable=true，M1 契约中注明供 M2 申请选教室）。
 * 只读调用，仍走类型化客户端。
 */
export const seatRoomsApi = createApi<SeatPaths>();

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
