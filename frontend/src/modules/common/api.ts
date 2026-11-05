import type { components } from "@/api/types/common";

// common 服务的客户端只有一个，定义在 core（登录与通知铃铛也要用）
export { commonApi } from "@/core/commonApi";
export type UserAdmin = components["schemas"]["UserAdmin"];
export type UserCreate = components["schemas"]["UserCreate"];
export type UserUpdate = components["schemas"]["UserUpdate"];
export type RoleOut = components["schemas"]["RoleOut"];
export type PermissionOut = components["schemas"]["PermissionOut"];
export type DeptOut = components["schemas"]["DeptOut"];
export type NotificationOut = components["schemas"]["NotificationOut"];
export type AuditLogOut = components["schemas"]["AuditLogOut"];

export const moduleLabel: Record<string, string> = {
  common: "公共",
  m1: "自习座位",
  m2: "教室申请",
  m3: "报修",
};
