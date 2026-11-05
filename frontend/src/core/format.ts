/**
 * 时间一律按业务时区（Asia/Shanghai，UTC+8）显示和输入，与浏览器所在时区无关。
 * 页面不要自己 toLocaleString 或拼时区偏移，统一用这里的函数。
 */

/** 业务时区，与后端 campus_common.timeutil.BIZ_TZ 一致。 */
export const BIZ_TIME_ZONE = "Asia/Shanghai";
/** 业务时区的 UTC 偏移（上海不实行夏令时，固定 +08:00） */
const BIZ_UTC_OFFSET = "+08:00";

/** 后端返回带时区的 ISO 时间，按业务时区显示。 */
export function fmtTime(iso: string | null | undefined): string {
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

/**
 * 业务时区下某一时刻的日期（YYYY-MM-DD）与整点（0–23），与浏览器所在时区无关。
 * 不要用 toISOString() 取日期：那是 UTC 日期，北京时间 0–8 点会得到前一天。
 */
export function bizNow(at: Date = new Date()): { date: string; hour: number } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: BIZ_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(at)
      .map((part) => [part.type, part.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, hour: Number(parts.hour) };
}

/** 日期（YYYY-MM-DD）加减天数。 */
export function addDays(date: string, days: number): string {
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}
