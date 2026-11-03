"""座位搜索、按小时可用性和状态历史。"""

from datetime import date, datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import at_hour
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import room_service
from app import schemas as s
from app.models import Reservation, Room, RoomBlock, RoomOpenHour, Seat, SeatStatusLog

ACTIVE_STATUSES = ("booked", "checked_in")


def _validate_hours(start_hour: int, end_hour: int) -> None:
    if end_hour <= start_hour:
        raise AppError(400, "INVALID_TIME_RANGE", "结束小时必须晚于开始小时")


def _reservation_conflict(start_at: datetime, end_at: datetime):
    return exists(
        select(Reservation.id).where(
            Reservation.seat_id == Seat.id,
            Reservation.status.in_(ACTIVE_STATUSES),
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
    )


def _block_conflict(start_at: datetime, end_at: datetime):
    return exists(
        select(RoomBlock.id).where(
            RoomBlock.room_id == Room.id,
            RoomBlock.released_at.is_(None),
            RoomBlock.start_at < end_at,
            or_(RoomBlock.end_at.is_(None), RoomBlock.end_at > start_at),
        )
    )


async def search_seats(
    session: AsyncSession,
    user: CurrentUser,
    *,
    day: date,
    start_hour: int,
    end_hour: int,
    building: str | None,
    room_id: int | None,
    outlet: s.Outlet | None,
    params: PageParams,
) -> Page[s.SeatSearchItem]:
    _validate_hours(start_hour, end_hour)
    start_at = at_hour(day, start_hour)
    end_at = at_hour(day, end_hour)
    conditions = [
        Room.status == "enabled",
        Room.is_study_room.is_(True),
        Seat.status == "enabled",
        RoomOpenHour.weekday == day.weekday(),
        RoomOpenHour.open_hour <= start_hour,
        RoomOpenHour.close_hour >= end_hour,
        ~_reservation_conflict(start_at, end_at),
        ~_block_conflict(start_at, end_at),
    ]
    if not user.has("seat:room_manage"):
        conditions.append(or_(Room.dept_id.is_(None), Room.dept_id == user.dept_id))
    if building is not None:
        conditions.append(Room.building == building)
    if room_id is not None:
        conditions.append(Room.id == room_id)
    if outlet is not None:
        conditions.append(Seat.outlet == outlet)

    base = (
        select(Seat.id)
        .join(Room, Room.id == Seat.room_id)
        .join(RoomOpenHour, RoomOpenHour.room_id == Room.id)
    )
    total = await session.scalar(select(func.count()).select_from(base.where(*conditions).subquery()))
    rows = (
        await session.execute(
            select(Seat, Room)
            .join(Room, Room.id == Seat.room_id)
            .join(RoomOpenHour, RoomOpenHour.room_id == Room.id)
            .where(*conditions)
            .order_by(Room.building, Room.name, Seat.code, Seat.id)
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    hours = await room_service.hours_by_room(session, list({room.id for _, room in rows}))
    items = [
        s.SeatSearchItem(
            seat=s.Seat.model_validate(seat, from_attributes=True),
            room=room_service.room_out(room, hours[room.id]),
        )
        for seat, room in rows
    ]
    return page_of(items, total or 0, params)


def _reservation_source(reservations: list[Reservation], hour_start: datetime, hour_end: datetime):
    for reservation in reservations:
        if reservation.start_at < hour_end and reservation.end_at > hour_start:
            return reservation
    return None


def _block_source(blocks: list[RoomBlock], hour_start: datetime, hour_end: datetime):
    for block in blocks:
        if block.start_at < hour_end and (block.end_at is None or block.end_at > hour_start):
            return block
    return None


async def room_availability(
    session: AsyncSession, user: CurrentUser, room_id: int, day: date
) -> list[s.SeatAvailability]:
    room = await session.get(Room, room_id)
    can_manage = user.has("seat:room_manage")
    if room is None:
        raise not_found("教室", room_id)
    if not can_manage and (room.status != "enabled" or (room.dept_id not in (None, user.dept_id))):
        raise not_found("教室", room_id)

    seats = (
        await session.scalars(select(Seat).where(Seat.room_id == room_id).order_by(Seat.code, Seat.id))
    ).all()
    open_hour = await session.scalar(
        select(RoomOpenHour).where(
            RoomOpenHour.room_id == room_id,
            RoomOpenHour.weekday == day.weekday(),
        )
    )
    day_start = at_hour(day, 0)
    day_end = at_hour(day, 24)
    reservations = (
        await session.scalars(
            select(Reservation)
            .where(
                Reservation.room_id == room_id,
                Reservation.status.in_(ACTIVE_STATUSES),
                Reservation.start_at < day_end,
                Reservation.end_at > day_start,
            )
            .order_by(Reservation.start_at, Reservation.id)
        )
    ).all()
    blocks = (
        await session.scalars(
            select(RoomBlock)
            .where(
                RoomBlock.room_id == room_id,
                RoomBlock.released_at.is_(None),
                RoomBlock.start_at < day_end,
                or_(RoomBlock.end_at.is_(None), RoomBlock.end_at > day_start),
            )
            .order_by(RoomBlock.start_at, RoomBlock.id)
        )
    ).all()

    result: list[s.SeatAvailability] = []
    for seat in seats:
        seat_reservations = [row for row in reservations if row.seat_id == seat.id]
        hours: list[s.HourState] = []
        for hour in range(24):
            hour_start = at_hour(day, hour)
            hour_end = hour_start + timedelta(hours=1)
            if open_hour is None or hour < open_hour.open_hour or hour >= open_hour.close_hour:
                hours.append(s.HourState(hour=hour, state="closed"))
                continue
            if room.status != "enabled" or seat.status != "enabled":
                hours.append(s.HourState(hour=hour, state="blocked", source="M1_ADMIN"))
                continue
            block = _block_source(blocks, hour_start, hour_end)
            if block is not None:
                hours.append(s.HourState(hour=hour, state="blocked", source=block.source))
                continue
            reservation = _reservation_source(seat_reservations, hour_start, hour_end)
            if reservation is not None:
                hours.append(s.HourState(hour=hour, state="reserved", source="M1_RESERVATION"))
                continue
            hours.append(s.HourState(hour=hour, state="free"))
        result.append(s.SeatAvailability(seat_id=seat.id, hours=hours))
    return result


async def status_history(session: AsyncSession, seat_id: int) -> list[s.StatusHistoryItem]:
    seat = await session.get(Seat, seat_id)
    if seat is None:
        raise not_found("座位", seat_id)
    rows = (
        await session.scalars(
            select(SeatStatusLog)
            .where(SeatStatusLog.seat_id == seat_id)
            .order_by(SeatStatusLog.at.desc(), SeatStatusLog.id.desc())
        )
    ).all()
    return [s.StatusHistoryItem.model_validate(row, from_attributes=True) for row in rows]
