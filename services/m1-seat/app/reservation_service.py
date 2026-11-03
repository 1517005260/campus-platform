"""个人预约的创建、取消、查询和历史复订。"""

from datetime import datetime

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.events import ReservationCancelled
from campus_common.outbox import add_event
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import at_hour, now
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import room_service
from app import schemas as s
from app.config import settings
from app.models import Outbox, Reservation, Room, RoomBlock, RoomOpenHour, Seat, SeatStatusLog, Violation
from app.rules import aload_rules

PRODUCER = settings.service_name
ACTIVE_STATUSES = ("booked", "checked_in")


def _constraint_name(exc: IntegrityError) -> str:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) or str(exc.orig)


def _reservation_out(row: Reservation) -> s.Reservation:
    return s.Reservation.model_validate(row, from_attributes=True)


async def _available_seat(
    session: AsyncSession,
    user: CurrentUser,
    seat_id: int,
    start_at: datetime,
    end_at: datetime,
) -> tuple[Seat, Room]:
    seat = await session.get(Seat, seat_id)
    if seat is None:
        raise not_found("座位", seat_id)
    room = await session.scalar(select(Room).where(Room.id == seat.room_id).with_for_update())
    if room is None:
        raise not_found("教室", seat.room_id)
    if room.status != "enabled" or seat.status != "enabled" or not room.is_study_room:
        raise AppError(409, "SEAT_NOT_AVAILABLE", "座位当前不可预约")
    if room.dept_id is not None and room.dept_id != user.dept_id:
        raise AppError(403, "DEPT_RESTRICTED", "该自习室只对本院系开放")

    open_hour = await session.scalar(
        select(RoomOpenHour).where(
            RoomOpenHour.room_id == room.id,
            RoomOpenHour.weekday == start_at.weekday(),
        )
    )
    if (
        open_hour is None
        or start_at.hour < open_hour.open_hour
        or end_at > at_hour(start_at.date(), open_hour.close_hour)
    ):
        raise AppError(400, "OUTSIDE_OPEN_HOURS", "预约时段不在开放时间内")

    block = await session.scalar(
        select(RoomBlock.id)
        .where(
            RoomBlock.room_id == room.id,
            RoomBlock.released_at.is_(None),
            RoomBlock.start_at < end_at,
            or_(RoomBlock.end_at.is_(None), RoomBlock.end_at > start_at),
        )
        .limit(1)
    )
    if block is not None:
        raise AppError(409, "SEAT_NOT_AVAILABLE", "教室在该时段已被占用")

    seat_conflict = await session.scalar(
        select(Reservation.id)
        .where(
            Reservation.seat_id == seat.id,
            Reservation.status.in_(ACTIVE_STATUSES),
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
        .limit(1)
    )
    if seat_conflict is not None:
        raise AppError(409, "SEAT_NOT_AVAILABLE", "该座位在所选时段已被预约")

    user_conflict = await session.scalar(
        select(Reservation.id)
        .where(
            Reservation.user_id == user.id,
            Reservation.status.in_(ACTIVE_STATUSES),
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
        .limit(1)
    )
    if user_conflict is not None:
        raise AppError(409, "USER_TIME_CONFLICT", "你在该时段已有预约")
    return seat, room


async def create_reservation(
    session: AsyncSession,
    user: CurrentUser,
    seat_id: int,
    body: s.HourRange,
) -> s.Reservation:
    start_at = at_hour(body.date, body.start_hour)
    end_at = at_hour(body.date, body.end_hour)
    if start_at <= now():
        raise AppError(400, "RESERVATION_IN_PAST", "不能预约已经开始的时段")
    try:
        async with session.begin():
            rules = await aload_rules(session)
            if body.end_hour - body.start_hour > rules.max_hours:
                raise AppError(400, "INVALID_DURATION", f"单次预约不能超过 {rules.max_hours} 小时")
            seat, room = await _available_seat(session, user, seat_id, start_at, end_at)
            reservation = Reservation(
                user_id=user.id,
                seat_id=seat.id,
                room_id=room.id,
                start_at=start_at,
                end_at=end_at,
                status="booked",
            )
            session.add(reservation)
            await session.flush()
            session.add(
                SeatStatusLog(
                    seat_id=seat.id,
                    at=now(),
                    state="reserved",
                    source="M1_RESERVATION",
                    ref_id=reservation.id,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
    except IntegrityError as exc:
        constraint = _constraint_name(exc)
        if "no_seat_overlap" in constraint:
            raise AppError(409, "SEAT_NOT_AVAILABLE", "该座位在所选时段已被预约") from exc
        if "no_user_overlap" in constraint:
            raise AppError(409, "USER_TIME_CONFLICT", "你在该时段已有预约") from exc
        raise
    return _reservation_out(reservation)


async def rebook(
    session: AsyncSession,
    user: CurrentUser,
    reservation_id: int,
    body: s.HourRange,
) -> s.Reservation:
    async with session.begin():
        previous = await session.get(Reservation, reservation_id)
        if previous is None or previous.user_id != user.id:
            raise not_found("预约", reservation_id)
        seat_id = previous.seat_id
    return await create_reservation(session, user, seat_id, body)


async def cancel_reservation(
    session: AsyncSession,
    user: CurrentUser,
    reservation_id: int,
) -> s.Reservation:
    async with session.begin():
        reservation = await session.scalar(
            select(Reservation).where(Reservation.id == reservation_id).with_for_update()
        )
        if reservation is None or reservation.user_id != user.id:
            raise not_found("预约", reservation_id)
        if reservation.status != "booked":
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "当前预约状态不能取消")
        if reservation.start_at <= now():
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "预约已经开始，不能取消")

        reservation.status = "cancelled"
        reservation.cancel_reason = "USER"
        session.add(
            SeatStatusLog(
                seat_id=reservation.seat_id,
                at=now(),
                state="released",
                source="M1_RESERVATION",
                ref_id=reservation.id,
                start_at=reservation.start_at,
                end_at=reservation.end_at,
            )
        )
        add_event(
            session,
            Outbox,
            PRODUCER,
            ReservationCancelled(
                reservation_id=reservation.id,
                user_id=reservation.user_id,
                reason="USER",
            ),
        )
        await session.flush()
    return _reservation_out(reservation)


async def _details(session: AsyncSession, rows: list[Reservation]) -> list[s.ReservationDetail]:
    seat_ids = {row.seat_id for row in rows}
    room_ids = {row.room_id for row in rows}
    seats = (await session.scalars(select(Seat).where(Seat.id.in_(seat_ids)))).all() if seat_ids else []
    rooms = (await session.scalars(select(Room).where(Room.id.in_(room_ids)))).all() if room_ids else []
    seat_map = {row.id: row for row in seats}
    room_map = {row.id: row for row in rooms}
    hours = await room_service.hours_by_room(session, list(room_ids))
    return [
        s.ReservationDetail(
            **_reservation_out(row).model_dump(),
            seat=s.Seat.model_validate(seat_map[row.seat_id], from_attributes=True),
            room=room_service.room_out(room_map[row.room_id], hours[row.room_id]),
        )
        for row in rows
    ]


async def my_reservations(
    session: AsyncSession,
    user: CurrentUser,
    *,
    status: s.ReservationStatus | None,
    params: PageParams,
) -> Page[s.ReservationDetail]:
    conditions = [Reservation.user_id == user.id]
    if status is not None:
        conditions.append(Reservation.status == status)
    total = await session.scalar(select(func.count()).select_from(Reservation).where(*conditions))
    rows = (
        await session.scalars(
            select(Reservation)
            .where(*conditions)
            .order_by(Reservation.start_at.desc(), Reservation.id.desc())
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    return page_of(await _details(session, list(rows)), total or 0, params)


async def my_violations(
    session: AsyncSession,
    user: CurrentUser,
    params: PageParams,
) -> Page[s.ViolationOut]:
    total = await session.scalar(
        select(func.count()).select_from(Violation).where(Violation.user_id == user.id)
    )
    rows = (
        await session.scalars(
            select(Violation)
            .where(Violation.user_id == user.id)
            .order_by(Violation.created_at.desc(), Violation.id.desc())
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    return page_of(
        [s.ViolationOut.model_validate(row, from_attributes=True) for row in rows],
        total or 0,
        params,
    )
