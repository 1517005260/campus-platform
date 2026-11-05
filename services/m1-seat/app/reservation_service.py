"""个人预约的创建、取消、查询和历史复订。可约规则来自 app.shared，与搜索一致。"""

from campus_common.auth import CurrentUser
from campus_common.db import constraint_errors
from campus_common.errors import AppError, not_found
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import now
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas as s
from app.models import Reservation, Room, Seat, SeatStatusLog, Violation
from app.rules import aload_rules
from app.shared import (
    active_reservations,
    check_slot,
    has_started,
    lock_room,
    own_reservation,
    release_reservation,
    seat_rules,
)

# 并发下由排除约束兜底拒绝的冲突，与预检查返回同样的错误码
OVERLAP_ERRORS = {
    "no_seat_overlap": (409, "SEAT_NOT_AVAILABLE", "该座位在所选时段已被预约"),
    "no_user_overlap": (409, "USER_TIME_CONFLICT", "你在该时段已有预约"),
}


async def create_reservation(
    session: AsyncSession,
    user: CurrentUser,
    seat_id: int,
    slot: s.HourRange,
) -> s.Reservation:
    with constraint_errors(OVERLAP_ERRORS):
        async with session.begin():
            start_at, end_at = check_slot(slot, await aload_rules(session), now())
            room_id = await session.scalar(select(Seat.room_id).where(Seat.id == seat_id))
            if room_id is None:
                raise not_found("座位", seat_id)
            # 锁住教室后再读座位与教室状态，与并发的整室占用、停用串行
            await lock_room(session, room_id)
            rules = seat_rules(user, slot, start_at, end_at)
            results = (
                await session.execute(
                    select(*(rule.holds for rule in rules))
                    .select_from(Seat)
                    .join(Room, Room.id == Seat.room_id)
                    .where(Seat.id == seat_id)
                )
            ).one()
            for rule, holds in zip(rules, results, strict=True):
                if not holds:
                    raise rule.error()
            user_conflict = await session.scalar(
                active_reservations(start_at, end_at)
                .where(Reservation.user_id == user.id)
                .with_only_columns(Reservation.id)
                .limit(1)
            )
            if user_conflict is not None:
                raise AppError(*OVERLAP_ERRORS["no_user_overlap"])

            reservation = Reservation(
                user_id=user.id,
                seat_id=seat_id,
                room_id=room_id,
                start_at=start_at,
                end_at=end_at,
                status="booked",
            )
            session.add(reservation)
            await session.flush()
            session.add(
                SeatStatusLog(
                    seat_id=seat_id,
                    at=now(),
                    state="reserved",
                    source="M1_RESERVATION",
                    ref_id=reservation.id,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
    return s.Reservation.model_validate(reservation, from_attributes=True)


async def rebook(
    session: AsyncSession,
    user: CurrentUser,
    reservation_id: int,
    slot: s.HourRange,
) -> s.Reservation:
    async with session.begin():
        seat_id = (await own_reservation(session, user, reservation_id)).seat_id
    return await create_reservation(session, user, seat_id, slot)


async def cancel_reservation(
    session: AsyncSession,
    user: CurrentUser,
    reservation_id: int,
) -> s.Reservation:
    async with session.begin():
        reservation = await own_reservation(session, user, reservation_id, for_update=True)
        if reservation.status != "booked":
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "当前预约状态不能取消")
        at = now()
        if has_started(reservation.start_at, at):
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "预约已经开始，不能取消")
        release_reservation(session, reservation, "USER", at=at)
        await session.flush()
    return s.Reservation.model_validate(reservation, from_attributes=True)


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
            .options(selectinload(Reservation.seat), selectinload(Reservation.room))
            .order_by(Reservation.start_at.desc(), Reservation.id.desc())
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    return page_of(
        [s.ReservationDetail.model_validate(row, from_attributes=True) for row in rows], total or 0, params
    )


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
