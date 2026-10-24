"""时间工具。业务时区固定为 Asia/Shanghai，数据库统一存 timestamptz。"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BIZ_TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(BIZ_TZ)


def at_hour(day: date, hour: int) -> datetime:
    """某天某个整点（业务时区）。hour 取 0–24，24 表示次日 0 点。"""
    return datetime.combine(day, time(0), BIZ_TZ) + timedelta(hours=hour)
