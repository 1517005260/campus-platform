/**
 * 申请人撤回申请（列表与详情共用）：审批中的申请"撤回"；已通过且尚未开始的申请"取消"，
 * 后端先释放 M1 的教室占用再改状态。两者是同一个 withdraw 接口，确认文案按状态区分。
 */
import { ElMessage } from "element-plus";

import { confirmAction } from "@/core/dialogs";
import { showError } from "@/core/http";

import { roomApi, type Application } from "./api";

/** 当前可做的撤回动作；不可撤回时为 null */
export function withdrawAction(a: Application, now = Date.now()): { label: string; confirm: string } | null {
  if (a.status === "pending") {
    return { label: "撤回", confirm: `撤回申请 #${a.id}？撤回后审批终止，不能恢复。` };
  }
  if (a.status === "approved" && now < Date.parse(a.start_at)) {
    return { label: "取消", confirm: `取消已通过的申请 #${a.id}？教室占用将被释放，不能恢复。` };
  }
  return null;
}

/** 确认后撤回；成功返回 true（调用方刷新），取消或失败返回 false */
export async function withdrawApplication(a: Application): Promise<boolean> {
  const action = withdrawAction(a);
  if (!action || !(await confirmAction(action.confirm, { action: `${action.label}申请` }))) return false;
  try {
    await roomApi.POST("/api/v1/room/applications/{application_id}/withdraw", {
      params: { path: { application_id: a.id } },
    });
    ElMessage.success(`已${action.label}`);
    return true;
  } catch (e) {
    showError(e);
    return false;
  }
}
