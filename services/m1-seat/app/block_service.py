"""整室占用、释放和跨模块查询。"""

from datetime import datetime

from campus_common.errors import AppError, not_found
from campus_common.events import AuditRecord, NotificationSend, Ref, ReservationCancelled
from campus_common.outbox import add_event
from campus_common.timeutil import now
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.config import settings
from app.models import (
    Outbox,
    Reservation,
    Room,
    RoomBlock,
    RoomOpenHour,
    Seat,
    SeatStatusLog,
    Violation,
)

PRODUCER = settings.service_name
ACTIVE_STATUSES = ("booked", "checked_in")
CALLER_SOURCE = {"m2-room": "M2_OCCUPY", "m3-repair": "M3_MAINTENANCE"}
CANCEL_REASON = {"M2_OCCUPY": "BLOCKED_BY_M2", "M3_MAINTENANCE": "BLOCKED_BY_M3"}


def _validate_source(caller: str, source: str) -> None:
    expected = CALLER_SOURCE.get(caller)
    if expected != source:
        raise AppError(403, "BLOCK_SOURCE_FORBIDDEN", f"{caller} 不能创建 {source} 占用")


def _reservation_out(row: Reservation) -> s.Reservation:
    return s.Reservation.model_validate(row, from_attributes=True)


async def _room_out(session: AsyncSession, room: Room) -> s.Room:
    hours = (
        await session.scalars(
            select(RoomOpenHour).where(RoomOpenHour.room_id == room.id).order_by(RoomOpenHour.weekday)
        )
    ).all()
    return s.Room(
        id=room.id,
        building=room.building,
        floor=room.floor,
        name=room.name,
        type=room.type,
        dept_id=room.dept_id,
        capacity=room.capacity,
        is_study_room=room.is_study_room,
        is_whole_bookable=room.is_whole_bookable,
        open_hours=[
            s.OpenHour(weekday=row.weekday, open_hour=row.open_hour, close_hour=row.close_hour)
            for row in hours
        ],
        status=room.status,
    )


async def get_room(session: AsyncSession, room_id: int) -> s.Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise not_found("教室", room_id)
    return await _room_out(session, room)


async def create_block(
    session: AsyncSession, caller: str, body: s.InternalBlockCreate
) -> s.InternalBlockResult:
    _validate_source(caller, body.source)
    if body.end_at is not None and body.end_at <= body.start_at:
        raise AppError(400, "INVALID_BLOCK_RANGE", "占用结束时间必须晚于开始时间")

    # 同一来源单号只允许有一个生命周期，不同幂等键也不能并发创建两份记录。
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"m1:block:{body.source}:{body.ref_id}"},
    )
    existing = await session.scalar(
        select(RoomBlock)
        .where(RoomBlock.source == body.source, RoomBlock.ref_id == body.ref_id)
        .with_for_update()
    )
    if existing is not None:
        same_request = (
            existing.room_id == body.room_id
            and existing.start_at == body.start_at
            and existing.end_at == body.end_at
            and existing.reason == body.reason
        )
        if not same_request:
            raise AppError(409, "BLOCK_REFERENCE_CONFLICT", "同一来源单号已用于不同的占用请求")
        return s.InternalBlockResult(block_id=existing.id, cancelled_reservations=[])

    room = await session.scalar(select(Room).where(Room.id == body.room_id).with_for_update())
    if room is None:
        raise not_found("教室", body.room_id)

    block = RoomBlock(
        room_id=body.room_id,
        source=body.source,
        ref_id=body.ref_id,
        start_at=body.start_at,
        end_at=body.end_at,
        reason=body.reason,
        created_by=caller,
    )
    session.add(block)
    await session.flush()

    conditions = [
        Reservation.room_id == body.room_id,
        Reservation.status.in_(ACTIVE_STATUSES),
        Reservation.end_at > body.start_at,
    ]
    if body.end_at is not None:
        conditions.append(Reservation.start_at < body.end_at)
    reservations = (
        await session.scalars(
            select(Reservation).where(*conditions).order_by(Reservation.id).with_for_update()
        )
    ).all()

    at = now()
    cancel_reason = CANCEL_REASON[body.source]
    for reservation in reservations:
        reservation.status = "cancelled"
        reservation.cancel_reason = cancel_reason
        session.add(
            SeatStatusLog(
                seat_id=reservation.seat_id,
                at=at,
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
            NotificationSend(
                user_ids=[reservation.user_id],
                template="seat.reservation_cancelled_by_block",
                params={
                    "reservation_id": reservation.id,
                    "start_at": reservation.start_at.isoformat(),
                    "end_at": reservation.end_at.isoformat(),
                    "block_source": body.source,
                    "block_ref_id": body.ref_id,
                    "reason": body.reason,
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
                reason="BLOCKED",
            ),
        )

    seat_ids = (
        await session.scalars(select(Seat.id).where(Seat.room_id == body.room_id).order_by(Seat.id))
    ).all()
    for seat_id in seat_ids:
        session.add(
            SeatStatusLog(
                seat_id=seat_id,
                at=at,
                state="blocked",
                source=body.source,
                ref_id=body.ref_id,
                start_at=body.start_at,
                end_at=body.end_at,
            )
        )

    add_event(
        session,
        Outbox,
        PRODUCER,
        AuditRecord(
            actor_type="service",
            actor_id=caller,
            module="m1",
            action="block.create",
            target_type="room_block",
            target_id=str(block.id),
            after={
                "room_id": body.room_id,
                "source": body.source,
                "ref_id": body.ref_id,
                "start_at": body.start_at.isoformat(),
                "end_at": body.end_at.isoformat() if body.end_at else None,
                "cancelled_reservation_ids": [reservation.id for reservation in reservations],
            },
        ),
    )
    return s.InternalBlockResult(
        block_id=block.id,
        cancelled_reservations=[_reservation_out(reservation) for reservation in reservations],
    )


async def release_block(session: AsyncSession, caller: str, source: str, ref_id: int) -> bool:
    _validate_source(caller, source)
    block = await session.scalar(
        select(RoomBlock).where(RoomBlock.source == source, RoomBlock.ref_id == ref_id).with_for_update()
    )
    if block is None or block.released_at is not None:
        return False

    released_at = now()
    block.released_at = released_at
    seat_ids = (
        await session.scalars(select(Seat.id).where(Seat.room_id == block.room_id).order_by(Seat.id))
    ).all()
    for seat_id in seat_ids:
        session.add(
            SeatStatusLog(
                seat_id=seat_id,
                at=released_at,
                state="unblocked",
                source=source,
                ref_id=ref_id,
                start_at=block.start_at,
                end_at=block.end_at,
            )
        )

    add_event(
        session,
        Outbox,
        PRODUCER,
        AuditRecord(
            actor_type="service",
            actor_id=caller,
            module="m1",
            action="block.release",
            target_type="room_block",
            target_id=str(block.id),
            before={"released_at": None},
            after={"released_at": released_at.isoformat()},
        ),
    )
    return True


async def room_reservations(
    session: AsyncSession, room_id: int, start_at: datetime, end_at: datetime
) -> list[s.Reservation]:
    if end_at <= start_at:
        raise AppError(400, "INVALID_TIME_RANGE", "结束时间必须晚于开始时间")
    room = await session.get(Room, room_id)
    if room is None:
        raise not_found("教室", room_id)
    rows = (
        await session.scalars(
            select(Reservation)
            .where(
                Reservation.room_id == room_id,
                Reservation.status.in_(ACTIVE_STATUSES),
                Reservation.start_at < end_at,
                Reservation.end_at > start_at,
            )
            .order_by(Reservation.start_at, Reservation.id)
        )
    ).all()
    return [_reservation_out(row) for row in rows]


async def violation_count(session: AsyncSession, user_id: int, since: datetime) -> s.InternalViolationCount:
    count = await session.scalar(
        select(func.count())
        .select_from(Violation)
        .where(Violation.user_id == user_id, Violation.created_at >= since)
    )
    return s.InternalViolationCount(user_id=user_id, count=count or 0)
