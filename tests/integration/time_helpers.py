"""集成测试不依赖服务代码，这里只放少量时间工具。"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def next_hour_iso(delta: timedelta) -> str:
    t = (datetime.now(TZ) + delta).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return t.isoformat()


def day_at_iso(days: int, hour: int) -> str:
    """今天之后第 days 天（业务时区）的整点，不随运行时刻变化，便于落在教室开放时间内。"""
    day = datetime.now(TZ).date() + timedelta(days=days)
    return datetime.combine(day, time(hour), TZ).isoformat()
