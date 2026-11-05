"""座位搜索、按小时可用性和状态历史。规则来自 app.shared，与创建预约一致。"""

from datetime import date

from campus_common.auth import CurrentUser
from campus_common.errors import not_found
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import at_hour, now
from sqlalchemy import DateTime, Integer, column, func, select, true, values
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import Reservation, Room, RoomBlock, Seat, SeatStatusLog
from app.rules import aload_rules
from app.shared import (
    active_reservations,
    check_slot,
    open_during,
    room_visible,
    seat_rules,
    seat_usable,
    unreleased_blocks,
)


async def search_seats(
    session: AsyncSession,
    user: CurrentUser,
    *,
    slot: s.HourRange,
    building: str | None,
    room_id: int | None,
    outlet: s.Outlet | None,
    params: PageParams,
) -> Page[s.SeatSearchItem]:
    start_at, end_at = check_slot(slot, await aload_rules(session), now())
    conditions = [rule.holds for rule in seat_rules(user, slot, start_at, end_at)]
    if building is not None:
        conditions.append(Room.building == building)
    if room_id is not None:
        conditions.append(Room.id == room_id)
    if outlet is not None:
        conditions.append(Seat.outlet == outlet)

    base = select(Seat, Room).join(Room, Room.id == Seat.room_id).where(*conditions)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(
            base.order_by(Room.building, Room.name, Seat.code, Seat.id)
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    items = [
        s.SeatSearchItem(
            seat=s.Seat.model_validate(seat, from_attributes=True),
            room=s.Room.model_validate(room, from_attributes=True),
        )
        for seat, room in rows
    ]
    return page_of(items, total or 0, params)


def _hour_state(
    hour: int, is_open: bool, usable: bool, block_source: str | None, reserved: bool
) -> s.HourState:
    if not is_open:
        return s.HourState(hour=hour, state="closed")
    if not usable:
        return s.HourState(hour=hour, state="blocked", source="M1_ADMIN")
    if block_source is not None:
        return s.HourState(hour=hour, state="blocked", source=block_source)
    if reserved:
        return s.HourState(hour=hour, state="reserved", source="M1_RESERVATION")
    return s.HourState(hour=hour, state="free")


async def room_availability(
    session: AsyncSession, user: CurrentUser, room_id: int, day: date
) -> list[s.SeatAvailability]:
    """每个座位每个整点的状态，各状态与搜索、预约使用同一组规则（开放时间、启用、占用、有效预约）。"""
    room = await session.get(Room, room_id)
    if room is None or not room_visible(room, user):
        raise not_found("教室", room_id)

    hour, start_at, end_at = (
        column("hour", Integer),
        column("start_at", DateTime(timezone=True)),
        column("end_at", DateTime(timezone=True)),
    )
    slots = values(hour, start_at, end_at, name="slots").data(
        [(h, at_hour(day, h), at_hour(day, h + 1)) for h in range(24)]
    )
    rows = (
        await session.execute(
            select(
                Seat.id,
                slots.c.hour,
                open_during(day.weekday(), slots.c.hour, slots.c.hour + 1),
                seat_usable(),
                unreleased_blocks(slots.c.start_at, slots.c.end_at)
                .where(RoomBlock.room_id == Room.id)
                .with_only_columns(RoomBlock.source)
                .order_by(RoomBlock.start_at, RoomBlock.id)
                .limit(1)
                .scalar_subquery(),
                active_reservations(slots.c.start_at, slots.c.end_at)
                .where(Reservation.seat_id == Seat.id)
                .exists(),
            )
            .select_from(Seat)
            .join(Room, Room.id == Seat.room_id)
            .join(slots, true())
            .where(Seat.room_id == room_id)
            .order_by(Seat.code, Seat.id, slots.c.hour)
        )
    ).all()

    result: dict[int, s.SeatAvailability] = {}
    for seat_id, *state in rows:
        result.setdefault(seat_id, s.SeatAvailability(seat_id=seat_id, hours=[])).hours.append(
            _hour_state(*state)
        )
    return list(result.values())


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
