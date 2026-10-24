"""M1 接口契约（请求与响应模型）。

这里的模型决定 OpenAPI，也就是 contracts/openapi/m1-seat.json。
Internal* 开头的模型属于跨模块契约，改动需要调用方（M2、M3）评审。
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

RoomType = Literal["classroom", "library", "other"]
Outlet = Literal["none", "fixed", "rail"]
ReservationStatus = Literal["booked", "checked_in", "completed", "cancelled", "no_show"]
BlockSource = Literal["M2_OCCUPY", "M3_MAINTENANCE"]
# 座位状态变化的写入来源：学生预约、管理员停用/启用、M2 整室占用、M3 维修下架
StatusSource = Literal["M1_RESERVATION", "M1_ADMIN", "M2_OCCUPY", "M3_MAINTENANCE"]


# ---------- 空间与座位 ----------
class OpenHour(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = 周一")
    open_hour: int = Field(ge=0, le=23)
    close_hour: int = Field(ge=1, le=24)


class RoomBase(BaseModel):
    building: str = Field(max_length=50, examples=["第三教学楼"])
    floor: int
    name: str = Field(max_length=50, examples=["H3106"])
    type: RoomType
    dept_id: int | None = Field(None, description="为空表示全校开放；否则只对本院系开放")
    capacity: int = Field(ge=1)
    is_study_room: bool = True
    is_whole_bookable: bool = Field(False, description="是否允许 M2 整教室申请")
    open_hours: list[OpenHour] = []


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    building: str | None = None
    floor: int | None = None
    name: str | None = None
    type: RoomType | None = None
    dept_id: int | None = None
    capacity: int | None = None
    is_study_room: bool | None = None
    is_whole_bookable: bool | None = None
    open_hours: list[OpenHour] | None = None
    status: Literal["enabled", "disabled"] | None = None


class Room(RoomBase):
    id: int
    status: Literal["enabled", "disabled"]


class SeatCreate(BaseModel):
    code: str = Field(max_length=20, examples=["A-01"])
    outlet: Outlet = "none"


class SeatUpdate(BaseModel):
    outlet: Outlet | None = None
    status: Literal["enabled", "disabled"] | None = None


class Seat(BaseModel):
    id: int
    room_id: int
    code: str
    outlet: Outlet = Field(description="none 无插座；fixed 靠近固定插座；rail 靠近移动导轨插座")
    status: Literal["enabled", "disabled"]


class RoomDetail(Room):
    seats: list[Seat]


class SeatSearchItem(BaseModel):
    seat: Seat
    room: Room


class HourState(BaseModel):
    hour: int
    state: Literal["free", "reserved", "blocked", "closed"]
    source: StatusSource | None = None


class SeatAvailability(BaseModel):
    seat_id: int
    hours: list[HourState]


# ---------- 预约 ----------
class HourRange(BaseModel):
    date: date
    start_hour: int = Field(ge=0, le=23, description="开始整点")
    end_hour: int = Field(ge=1, le=24, description="结束整点（不含）")

    @model_validator(mode="after")
    def _order(self):
        if self.end_hour <= self.start_hour:
            raise ValueError("end_hour 必须大于 start_hour")
        return self


class ReservationCreate(HourRange):
    seat_id: int


class Reservation(BaseModel):
    id: int
    user_id: int
    seat_id: int
    room_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    status: ReservationStatus
    cancel_reason: str | None = None
    checked_in_at: AwareDatetime | None = None


class ReservationDetail(Reservation):
    seat: Seat
    room: Room


class CheckInRequest(BaseModel):
    code: str = Field(description="教室屏幕上显示的签到码")


class CheckinCodeOut(BaseModel):
    room_id: int
    code: str
    qr_payload: str = Field(description="二维码内容，微信扫码签到用")
    valid_date: date


class ViolationOut(BaseModel):
    id: int
    reservation_id: int
    created_at: AwareDatetime


# ---------- 管理与统计 ----------
class SeatSettings(BaseModel):
    """可调系统参数，括号内为默认值。"""

    max_hours: int = Field(4, ge=1, le=24, description="单次预约最多小时数")
    remind_before_min: int = Field(15, ge=0, description="开始前多少分钟提醒")
    remind_late_min: int = Field(10, ge=0, description="开始后多少分钟未签到再次提醒")
    auto_cancel_min: int = Field(15, ge=1, description="开始后多少分钟未签到自动取消并记违约")


class RoomUsage(BaseModel):
    room_id: int
    utilization: float
    no_show_rate: float
    reservations: int


class UsageStats(BaseModel):
    utilization: float = Field(description="已签到小时数 / 可预约小时数")
    no_show_rate: float
    by_room: list[RoomUsage]
    by_hour: dict[int, float] = Field(description="各整点的平均利用率")


class StatusHistoryItem(BaseModel):
    at: AwareDatetime
    state: Literal["reserved", "released", "blocked", "unblocked"]
    source: StatusSource
    ref_id: int
    start_at: AwareDatetime | None
    end_at: AwareDatetime | None


# ---------- 跨模块契约（M2、M3 调用） ----------
class InternalBlockCreate(BaseModel):
    room_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime | None = Field(None, description="为空表示结束时间未知（维修中）")
    source: BlockSource
    ref_id: int = Field(description="M2 申请 ID 或 M3 工单 ID")
    reason: str = Field(max_length=200)


class InternalBlockResult(BaseModel):
    block_id: int
    cancelled_reservations: list[Reservation] = Field(
        description="因本次占用被取消的个人预约（已通知学生，不记违约）"
    )


class InternalReleaseResult(BaseModel):
    released: bool = Field(description="false 表示本来就没有该占用，重复调用也不报错")


class InternalViolationCount(BaseModel):
    user_id: int
    count: int
