"""教室、开放时间和座位主数据。

停用座位、停用教室或注销自习室（is_study_room 改为 false）后不能再被使用：尚未结束的有效预约
（booked / checked_in）一并取消（cancel_reason=ADMIN_DISABLED，不记违约，通知学生），
与整室占用取消预约的处理相同。
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from campus_common.auth import CurrentUser
from campus_common.db import constraint_errors
from campus_common.errors import AppError, not_found
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import now
from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas as s
from app.models import Reservation, Room, RoomOpenHour, Seat, SeatStatusLog
from app.shared import active_reservations, lock_room, release_reservation, room_usable, room_visible

AdminCause = Literal["seat_disabled", "room_disabled", "room_deregistered"]

DUPLICATE_ERRORS = {
    "uq_rooms_building_name": (409, "ROOM_ALREADY_EXISTS", "同一楼宇中的教室名称不能重复"),
    "uq_seats_room_id_code": (409, "SEAT_ALREADY_EXISTS", "同一教室中的座位编号不能重复"),
}


def _validate_hours(hours: Sequence[s.OpenHour]) -> None:
    weekdays = [row.weekday for row in hours]
    if len(weekdays) != len(set(weekdays)):
        raise AppError(400, "INVALID_OPEN_HOURS", "同一星期不能配置多条开放时间")


def _open_hour_rows(room_id: int, hours: Sequence[s.OpenHour]) -> list[RoomOpenHour]:
    return [
        RoomOpenHour(room_id=room_id, weekday=row.weekday, open_hour=row.open_hour, close_hour=row.close_hour)
        for row in hours
    ]


async def _room_out(session: AsyncSession, room_id: int) -> s.Room:
    """写操作提交后重新读取教室（含开放时间）。"""
    room = await session.scalar(
        select(Room).where(Room.id == room_id).execution_options(populate_existing=True)
    )
    return s.Room.model_validate(room, from_attributes=True)


async def list_rooms(
    session: AsyncSession,
    user: CurrentUser,
    *,
    building: str | None,
    type: s.RoomType | None,
    is_study_room: bool | None,
    is_whole_bookable: bool | None,
    params: PageParams,
) -> Page[s.Room]:
    conditions = []
    if building is not None:
        conditions.append(Room.building == building)
    if type is not None:
        conditions.append(Room.type == type)
    if is_study_room is not None:
        conditions.append(Room.is_study_room.is_(is_study_room))
    if is_whole_bookable is not None:
        conditions.append(Room.is_whole_bookable.is_(is_whole_bookable))
    if not user.has("seat:room_manage"):
        conditions.append(Room.status == "enabled")
        conditions.append(or_(Room.dept_id.is_(None), Room.dept_id == user.dept_id))

    statement = select(Room).where(*conditions)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rooms = (
        await session.scalars(
            statement.order_by(Room.building, Room.name, Room.id).offset(params.offset).limit(params.size)
        )
    ).all()
    return page_of([s.Room.model_validate(room, from_attributes=True) for room in rooms], total or 0, params)


async def get_room(session: AsyncSession, user: CurrentUser, room_id: int) -> s.RoomDetail:
    room = await session.scalar(select(Room).where(Room.id == room_id).options(selectinload(Room.seats)))
    if room is None or not room_visible(room, user):
        raise not_found("教室", room_id)
    return s.RoomDetail.model_validate(room, from_attributes=True)


async def create_room(session: AsyncSession, body: s.RoomCreate) -> s.Room:
    _validate_hours(body.open_hours)
    room = Room(**body.model_dump(exclude={"open_hours"}))
    with constraint_errors(DUPLICATE_ERRORS):
        async with session.begin():
            session.add(room)
            await session.flush()
            session.add_all(_open_hour_rows(room.id, body.open_hours))
    return await _room_out(session, room.id)


async def update_room(session: AsyncSession, room_id: int, body: s.RoomUpdate) -> s.Room:
    fields = body.model_fields_set
    if "open_hours" in fields:
        _validate_hours(body.open_hours)
    with constraint_errors(DUPLICATE_ERRORS):
        async with session.begin():
            await lock_room(session, room_id)
            usable = select(room_usable()).where(Room.id == room_id)
            was_usable = await session.scalar(usable)
            room = await session.get(Room, room_id)
            for field in fields - {"open_hours"}:
                setattr(room, field, getattr(body, field))
            if "open_hours" in fields:
                await session.execute(delete(RoomOpenHour).where(RoomOpenHour.room_id == room_id))
                session.add_all(_open_hour_rows(room_id, body.open_hours))
            await session.flush()
            is_usable = await session.scalar(usable)
            if is_usable != was_usable:
                at = now()
                seat_ids = (await session.scalars(select(Seat.id).where(Seat.room_id == room_id))).all()
                _log_admin_status(session, seat_ids, usable=is_usable, ref_id=room_id, at=at)
                if not is_usable:
                    cause = "room_disabled" if room.status == "disabled" else "room_deregistered"
                    await _cancel_unfinished(session, Reservation.room_id == room_id, cause, at)
            await session.flush()
    return await _room_out(session, room_id)


async def create_seat(session: AsyncSession, room_id: int, body: s.SeatCreate) -> s.Seat:
    seat = Seat(room_id=room_id, code=body.code, outlet=body.outlet)
    with constraint_errors(DUPLICATE_ERRORS):
        async with session.begin():
            if await session.scalar(select(Room.id).where(Room.id == room_id)) is None:
                raise not_found("教室", room_id)
            session.add(seat)
            await session.flush()
    return s.Seat.model_validate(seat, from_attributes=True)


async def update_seat(session: AsyncSession, seat_id: int, body: s.SeatUpdate) -> s.Seat:
    async with session.begin():
        room_id = await session.scalar(select(Seat.room_id).where(Seat.id == seat_id))
        if room_id is None:
            raise not_found("座位", seat_id)
        # 与该教室的新预约串行，停用后不会再有预约落到这个座位上
        await lock_room(session, room_id)
        seat = await session.scalar(select(Seat).where(Seat.id == seat_id).with_for_update())
        before_status = seat.status
        for field in body.model_fields_set:
            setattr(seat, field, getattr(body, field))
        if seat.status != before_status:
            at = now()
            _log_admin_status(session, [seat.id], usable=seat.status == "enabled", ref_id=seat.id, at=at)
            if seat.status == "disabled":
                await _cancel_unfinished(session, Reservation.seat_id == seat.id, "seat_disabled", at)
        await session.flush()
    return s.Seat.model_validate(seat, from_attributes=True)


def _log_admin_status(
    session: AsyncSession, seat_ids: Sequence[int], *, usable: bool, ref_id: int, at: datetime
) -> None:
    session.add_all(
        SeatStatusLog(
            seat_id=seat_id,
            at=at,
            state="unblocked" if usable else "blocked",
            source="M1_ADMIN",
            ref_id=ref_id,
            start_at=None,
            end_at=None,
        )
        for seat_id in seat_ids
    )


async def _cancel_unfinished(
    session: AsyncSession, scope: ColumnElement[bool], cause: AdminCause, at: datetime
) -> None:
    """取消停用范围内尚未结束的有效预约（end_at 晚于当前时刻）。

    cause 随通知发给学生，说明实际原因：座位停用、教室停用或自习室注销（教室同时停用并注销时按停用）。"""
    reservations = (
        await session.scalars(active_reservations(at).where(scope).order_by(Reservation.id).with_for_update())
    ).all()
    for reservation in reservations:
        release_reservation(
            session,
            reservation,
            "ADMIN_DISABLED",
            at=at,
            notify="seat.reservation_cancelled_by_admin",
            params={"cause": cause},
        )
