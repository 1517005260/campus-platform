/**
 * 确认框与输入框。ElMessageBox 在用户点"取消"或关闭时以 "cancel"/"close" reject，
 * 页面直接 await 会产生未捕获的异常；统一用这里的函数，取消返回 false / null。
 */
import { ElMessageBox, type ElMessageBoxOptions } from "element-plus";

/** 用户确认返回 true，取消或关闭返回 false。 */
export async function confirmAction(message: string, title = "确认", options?: ElMessageBoxOptions): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, options);
    return true;
  } catch {
    return false;
  }
}

/**
 * 输入一段文字，返回去掉首尾空白的内容；取消或关闭返回 null。
 * minLength / maxLength 与后端字段长度一致（按去掉首尾空白后的长度）；minLength 默认 0 即可以为空。
 */
export async function promptText(
  message: string,
  title: string,
  { minLength = 0, maxLength, ...options }: ElMessageBoxOptions & { minLength?: number; maxLength?: number } = {},
): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt(message, title, {
      inputValidator: (v: string | null) => {
        const text = (v ?? "").trim();
        if (text.length < minLength) return minLength === 1 ? "请填写内容" : `至少 ${minLength} 个字`;
        if (maxLength !== undefined && text.length > maxLength) return `不能超过 ${maxLength} 字`;
        return true;
      },
      ...options,
    });
    return (value ?? "").trim();
  } catch {
    return null;
  }
}
