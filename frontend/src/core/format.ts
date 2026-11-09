/**
 * 时间一律按业务时区（Asia/Shanghai，UTC+8）显示和输入，与浏览器所在时区无关。
 * 页面不要自己 toLocaleString 或拼时区偏移，统一用这里的函数。
 */

/** 业务时区，与后端 campus_common.timeutil.BIZ_TZ 一致。 */
export const BIZ_TIME_ZONE = "Asia/Shanghai";
/** 业务时区的 UTC 偏移（上海不实行夏令时，固定 +08:00） */
const BIZ_UTC_OFFSET = "+08:00";

/** 后端返回带时区的 ISO 时间，按业务时区显示。 */
export function fmtTime(iso: string | Date | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false, timeZone: BIZ_TIME_ZONE });
}

/**
 * 业务时区的墙上时间（YYYY-MM-DDTHH:mm:ss，例如日期时间选择器的值）转成带 +08:00 的 ISO 时间，
 * 用于提交给要求带时区的接口参数。
 */
export function bizIso(wallTime: string): string {
  return `${wallTime}${BIZ_UTC_OFFSET}`;
}

/** 业务时区某天的整点（0–24，24 即次日 0 点）转成带 +08:00 的 ISO 时间。 */
export function bizHourIso(date: string, hour: number): string {
  const [day, h] = hour === 24 ? [addDays(date, 1), 0] : [date, hour];
  return bizIso(`${day}T${String(h).padStart(2, "0")}:00:00`);
}

/** 某一时刻在业务时区的各个字段（年月日时分秒，均为补零的字符串）。 */
function bizParts(at: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: BIZ_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(at)
      .map((part) => [part.type, part.value]),
  );
}

/**
 * 业务时区下某一时刻的日期（YYYY-MM-DD）与整点（0–23），与浏览器所在时区无关。
 * 不要用 toISOString() 取日期：那是 UTC 日期，北京时间 0–8 点会得到前一天。
 */
export function bizNow(at: Date = new Date()): { date: string; hour: number } {
  const p = bizParts(at);
  return { date: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) };
}

/** 某一时刻在业务时区的墙上时间（YYYY-MM-DDTHH:mm:ss），作为日期时间选择器的值。 */
export function bizWallTime(at: Date = new Date()): string {
  const p = bizParts(at);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

/** 日期（YYYY-MM-DD）加减天数。 */
export function addDays(date: string, days: number): string {
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

/** 日期（YYYY-MM-DD）是星期几，0 = 周一（与后端 OpenHour.weekday 一致）。 */
export function weekdayOf(date: string): number {
  // 纯日期按 UTC 解析再取星期，避免浏览器时区把日期挪一天
  return (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
}

/**
 * 日期选择器面板格子的 Date（浏览器本地零点）转成它所表示的日期 YYYY-MM-DD，
 * 用于 disabled-date 与业务日期比较。
 */
export function pickerDate(cell: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${cell.getFullYear()}-${pad(cell.getMonth() + 1)}-${pad(cell.getDate())}`;
}

/** 日期选择器 disabled-date：禁止选业务时区今天之前的日期。 */
export function isPastDate(cell: Date): boolean {
  return pickerDate(cell) < bizNow().date;
}
