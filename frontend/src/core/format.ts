/** 后端返回带时区的 ISO 时间，显示为本地时间。 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}
