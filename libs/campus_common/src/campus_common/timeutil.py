"""时间工具。业务时区固定为 Asia/Shanghai，数据库统一存 timestamptz。

从带时区的时间取日期、整点或星期时，先用 to_biz() 换到业务时区，不要直接对任意时区的值调用
.date() / .hour：同一时刻在 UTC 下可能还是前一天。
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, model_validator

BIZ_TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(BIZ_TZ)


def at_hour(day: date, hour: int) -> datetime:
    """某天某个整点（业务时区）。hour 取 0–24，24 表示次日 0 点。"""
    return datetime.combine(day, time(0), BIZ_TZ) + timedelta(hours=hour)


def to_biz(moment: datetime) -> datetime:
    """同一时刻在业务时区下的表示。不接受无时区时间，避免按服务器本地时区误换算。"""
    if moment.utcoffset() is None:
        raise ValueError(f"需要带时区的时间：{moment!r}")
    return moment.astimezone(BIZ_TZ)


class TimeRangeModel(BaseModel):
    """时段 [start_at, end_at) 的校验基类：end_at 必须晚于 start_at，否则校验失败（接口返回 422）。

    子类自己声明 start_at 与 end_at 字段（end_at 可以是可选的，None 表示无限期），基类不带字段，
    因此不改变子类的字段顺序和生成的 OpenAPI。"""

    @model_validator(mode="after")
    def _end_after_start(self):
        end_at = self.end_at  # type: ignore[attr-defined]
        if end_at is not None and end_at <= self.start_at:  # type: ignore[attr-defined]
            raise ValueError("end_at 必须晚于 start_at")
        return self
