"""M1 内部共用的规则、查询与动作。

搜索、按小时可用性、创建预约、整室占用和管理员停用都从这里取规则，保证同一件事只有一种判断：

- overlaps()：左闭右开时段是否相交，是所有冲突查询的唯一谓词；
- check_slot()：与座位无关的时段规则（未开始、时长），搜索与创建预约共用；
- seat_rules()：座位在某时段对某用户是否可约，每条规则带自己的错误码；
- release_reservation()：取消或标记未签到时释放座位，写状态日志与 outbox。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.events import NotificationSend, Ref, ReservationCancelled
from campus_common.outbox import add_event
from campus_common.timeutil import at_hour
from sqlalchemy import ColumnElement, Select, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.config import settings
from app.models import (
    ACTIVE_STATUSES,
    Outbox,
    Reservation,
    Room,
    RoomBlock,
    RoomOpenHour,
    Seat,
    SeatStatusLog,
)

PRODUCER = settings.service_name


# ---------- 时段与冲突 ----------
def overlaps(start_col, end_col, start_at, end_at) -> ColumnElement[bool]:
    """[start_col, end_col) 与 [start_at, end_at) 相交。列 end_col 为 NULL 或参数 end_at 为 None 表示无限期。

    start_at / end_at 可以是时间值，也可以是另一张表的列。"""
    condition = or_(end_col.is_(None), end_col > start_at)
    if end_at is None:
        return condition
    return and_(start_col < end_at, condition)


def active_reservations(start_at, end_at=None) -> Select[tuple[Reservation]]:
    """与时段重叠的有效预约（booked / checked_in），调用方再按座位、教室或用户过滤。"""
    return select(Reservation).where(
        Reservation.status.in_(ACTIVE_STATUSES),
        overlaps(Reservation.start_at, Reservation.end_at, start_at, end_at),
    )


def unreleased_blocks(start_at, end_at) -> Select[tuple[RoomBlock]]:
    """与时段重叠、尚未释放的整室占用，调用方再按教室过滤。"""
    return select(RoomBlock).where(
        RoomBlock.released_at.is_(None),
        overlaps(RoomBlock.start_at, RoomBlock.end_at, start_at, end_at),
    )


def has_started(start_at: datetime, at: datetime) -> bool:
    """开始时刻已到（含正好开始的这一刻）：不能再预约，也不能再由学生取消。"""
    return start_at <= at


def check_slot(slot: s.HourRange, rules: s.SeatSettings, at: datetime) -> tuple[datetime, datetime]:
    """与座位无关的时段规则，返回时段的起止时间。搜索与创建预约共用，错误码一致。"""
    start_at = at_hour(slot.date, slot.start_hour)
    if has_started(start_at, at):
        raise AppError(400, "RESERVATION_IN_PAST", "不能预约已经开始的时段")
    if slot.end_hour - slot.start_hour > rules.max_hours:
        raise AppError(400, "INVALID_DURATION", f"单次预约不能超过 {rules.max_hours} 小时")
    return start_at, at_hour(slot.date, slot.end_hour)


# ---------- 座位可约规则 ----------
def room_usable() -> ColumnElement[bool]:
    """教室启用且登记为自习室。停用或注销（is_study_room 改为 false）都使它不可用。"""
    return and_(Room.status == "enabled", Room.is_study_room.is_(True))


def seat_usable() -> ColumnElement[bool]:
    """座位所在教室可用且座位启用（M1_ADMIN 维护的可用性）。"""
    return and_(room_usable(), Seat.status == "enabled")


def dept_allows(user: CurrentUser) -> ColumnElement[bool]:
    """院系自习室只对本院系用户开放。"""
    return or_(Room.dept_id.is_(None), Room.dept_id == user.dept_id)


def open_during(weekday: int, start_hour, end_hour) -> ColumnElement[bool]:
    """时段完全落在该教室当天的开放时间内；没有开放时间记录的日子不开放。"""
    return exists().where(
        RoomOpenHour.room_id == Room.id,
        RoomOpenHour.weekday == weekday,
        RoomOpenHour.open_hour <= start_hour,
        RoomOpenHour.close_hour >= end_hour,
    )


@dataclass(frozen=True)
class SeatRule:
    holds: ColumnElement[bool]  # 在含 Seat、Room 的查询中求值
    status: int
    code: str
    message: str

    def error(self) -> AppError:
        return AppError(self.status, self.code, self.message)


def seat_rules(user: CurrentUser, slot: s.HourRange, start_at: datetime, end_at: datetime) -> list[SeatRule]:
    """座位在该时段对该用户可约的全部条件，按报错优先级排列。"""
    return [
        SeatRule(seat_usable(), 409, "SEAT_NOT_AVAILABLE", "座位当前不可预约"),
        SeatRule(dept_allows(user), 403, "DEPT_RESTRICTED", "该自习室只对本院系开放"),
        SeatRule(
            open_during(slot.date.weekday(), slot.start_hour, slot.end_hour),
            400,
            "OUTSIDE_OPEN_HOURS",
            "预约时段不在开放时间内",
        ),
        SeatRule(
            ~unreleased_blocks(start_at, end_at).where(RoomBlock.room_id == Room.id).exists(),
            409,
            "SEAT_NOT_AVAILABLE",
            "教室在该时段已被占用",
        ),
        SeatRule(
            ~active_reservations(start_at, end_at).where(Reservation.seat_id == Seat.id).exists(),
            409,
            "SEAT_NOT_AVAILABLE",
            "该座位在所选时段已被预约",
        ),
    ]


def room_visible(room: Room, user: CurrentUser) -> bool:
    """教室对用户是否可见：管理员看全部；其他人只看启用且院系允许的教室。"""
    if user.has("seat:room_manage"):
        return True
    return room.status == "enabled" and room.dept_id in (None, user.dept_id)


async def lock_room(session: AsyncSession, room_id: int) -> None:
    """锁住教室行。预约、整室占用和停用都先锁教室，同一教室的这些操作串行执行。"""
    if await session.scalar(select(Room.id).where(Room.id == room_id).with_for_update()) is None:
        raise not_found("教室", room_id)


async def own_reservation(
    session: AsyncSession, user: CurrentUser, reservation_id: int, *, for_update: bool = False
) -> Reservation:
    """当前用户自己的预约；不存在或属于他人时一律 404，不暴露别人的预约是否存在。

    for_update=True 时锁住该行，供取消、签到这类状态迁移在锁内检查状态。"""
    statement = select(Reservation).where(Reservation.id == reservation_id)
    if for_update:
        statement = statement.with_for_update()
    reservation = await session.scalar(statement)
    if reservation is None or reservation.user_id != user.id:
        raise not_found("预约", reservation_id)
    return reservation


# ---------- 释放预约 ----------
@dataclass(frozen=True)
class Release:
    status: str  # 预约的新状态
    event_reason: str  # m1.reservation.cancelled 的 reason
    log_source: str  # released 状态日志的写入来源


RELEASES = {
    "USER": Release("cancelled", "USER", "M1_RESERVATION"),
    "NO_CHECK_IN": Release("no_show", "NO_SHOW", "M1_RESERVATION"),
    "BLOCKED_BY_M2": Release("cancelled", "BLOCKED", "M1_RESERVATION"),
    "BLOCKED_BY_M3": Release("cancelled", "BLOCKED", "M1_RESERVATION"),
    "ADMIN_DISABLED": Release("cancelled", "ADMIN", "M1_ADMIN"),
}


def release_reservation(
    session,
    reservation: Reservation,
    cancel_reason: str,
    *,
    at: datetime,
    notify: str | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    """取消预约（或标记未签到）并释放座位。

    写 released 日志（ref_id 为预约 ID），发 m1.reservation.cancelled；notify 不为空时给学生发该模板的通知。
    只修改会话，同步、异步会话都可用，调用方负责提交；违约由调用方记录。"""
    release = RELEASES[cancel_reason]
    reservation.status = release.status
    reservation.cancel_reason = cancel_reason
    session.add(
        SeatStatusLog(
            seat_id=reservation.seat_id,
            at=at,
            state="released",
            source=release.log_source,
            ref_id=reservation.id,
            start_at=reservation.start_at,
            end_at=reservation.end_at,
        )
    )
    if notify is not None:
        add_event(
            session,
            Outbox,
            PRODUCER,
            NotificationSend(
                user_ids=[reservation.user_id],
                template=notify,
                params={
                    "reservation_id": reservation.id,
                    "start_at": reservation.start_at.isoformat(),
                    "end_at": reservation.end_at.isoformat(),
                    **(params or {}),
                },
                ref=Ref(module="m1", type="reservation", id=reservation.id),
            ),
        )
    add_event(
        session,
        Outbox,
        PRODUCER,
        ReservationCancelled(
            reservation_id=reservation.id,
            user_id=reservation.user_id,
            reason=release.event_reason,
        ),
    )
