"""整室占用、释放和跨模块查询。"""

from datetime import datetime

from campus_common.errors import AppError, not_found
from campus_common.events import AuditRecord
from campus_common.outbox import add_event
from campus_common.timeutil import now
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import Outbox, Reservation, Room, RoomBlock, Seat, SeatStatusLog, Violation
from app.shared import PRODUCER, active_reservations, lock_room, release_reservation

CALLER_SOURCE = {"m2-room": "M2_OCCUPY", "m3-repair": "M3_MAINTENANCE"}
CANCEL_REASON = {"M2_OCCUPY": "BLOCKED_BY_M2", "M3_MAINTENANCE": "BLOCKED_BY_M3"}


def _validate_source(caller: str, source: str) -> None:
    if CALLER_SOURCE.get(caller) != source:
        raise AppError(403, "BLOCK_SOURCE_FORBIDDEN", f"{caller} 不能操作 {source} 占用")


async def get_room(session: AsyncSession, room_id: int) -> s.Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise not_found("教室", room_id)
    return s.Room.model_validate(room, from_attributes=True)


async def _existing_block(session: AsyncSession, body: s.InternalBlockCreate) -> s.InternalBlockResult:
    """(source, ref_id) 已有记录：同一请求返回原占用；生命周期已结束或内容不同则拒绝。"""
    existing = await session.scalar(
        select(RoomBlock).where(RoomBlock.source == body.source, RoomBlock.ref_id == body.ref_id)
    )
    if existing.released_at is not None:
        raise AppError(409, "BLOCK_ALREADY_RELEASED", "该来源单号的占用已释放，不能再次占用")
    same_request = (
        existing.room_id == body.room_id
        and existing.start_at == body.start_at
        and existing.end_at == body.end_at
        and existing.reason == body.reason
    )
    if not same_request:
        raise AppError(409, "BLOCK_REFERENCE_CONFLICT", "同一来源单号已用于不同的占用请求")
    return s.InternalBlockResult(block_id=existing.id, cancelled_reservations=[])


async def create_block(
    session: AsyncSession, caller: str, body: s.InternalBlockCreate
) -> s.InternalBlockResult:
    _validate_source(caller, body.source)
    await lock_room(session, body.room_id)

    # (source, ref_id) 唯一约束保证同一单号只有一个占用生命周期；并发插入时后到的一方在这里跳过
    block_id = await session.scalar(
        insert(RoomBlock)
        .values(
            room_id=body.room_id,
            source=body.source,
            ref_id=body.ref_id,
            start_at=body.start_at,
            end_at=body.end_at,
            reason=body.reason,
            created_by=caller,
        )
        .on_conflict_do_nothing(index_elements=[RoomBlock.source, RoomBlock.ref_id])
        .returning(RoomBlock.id)
    )
    if block_id is None:
        return await _existing_block(session, body)

    reservations = (
        await session.scalars(
            active_reservations(body.start_at, body.end_at)
            .where(Reservation.room_id == body.room_id)
            .order_by(Reservation.id)
            .with_for_update()
        )
    ).all()
    at = now()
    for reservation in reservations:
        release_reservation(
            session,
            reservation,
            CANCEL_REASON[body.source],
            at=at,
            notify="seat.reservation_cancelled_by_block",
            params={"block_source": body.source, "block_ref_id": body.ref_id, "reason": body.reason},
        )

    seat_ids = (
        await session.scalars(select(Seat.id).where(Seat.room_id == body.room_id).order_by(Seat.id))
    ).all()
    session.add_all(
        SeatStatusLog(
            seat_id=seat_id,
            at=at,
            state="blocked",
            source=body.source,
            ref_id=body.ref_id,
            start_at=body.start_at,
            end_at=body.end_at,
        )
        for seat_id in seat_ids
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
            target_id=str(block_id),
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
        block_id=block_id,
        cancelled_reservations=[
            s.Reservation.model_validate(reservation, from_attributes=True) for reservation in reservations
        ],
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
    session.add_all(
        SeatStatusLog(
            seat_id=seat_id,
            at=released_at,
            state="unblocked",
            source=source,
            ref_id=ref_id,
            start_at=block.start_at,
            end_at=block.end_at,
        )
        for seat_id in seat_ids
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
    session: AsyncSession, room_id: int, span: s.InternalTimeRange
) -> list[s.Reservation]:
    if await session.scalar(select(Room.id).where(Room.id == room_id)) is None:
        raise not_found("教室", room_id)
    rows = (
        await session.scalars(
            active_reservations(span.start_at, span.end_at)
            .where(Reservation.room_id == room_id)
            .order_by(Reservation.start_at, Reservation.id)
        )
    ).all()
    return [s.Reservation.model_validate(row, from_attributes=True) for row in rows]


async def violation_count(session: AsyncSession, user_id: int, since: datetime) -> s.InternalViolationCount:
    count = await session.scalar(
        select(func.count())
        .select_from(Violation)
        .where(Violation.user_id == user_id, Violation.created_at >= since)
    )
    return s.InternalViolationCount(user_id=user_id, count=count or 0)
