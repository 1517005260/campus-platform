"""集成测试不依赖服务代码，这里只放少量时间工具。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def next_hour_iso(delta: timedelta) -> str:
    t = (datetime.now(TZ) + delta).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return t.isoformat()
