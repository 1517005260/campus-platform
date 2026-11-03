"""每日签到码与预约签到。"""

import hmac
import secrets
from datetime import datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.timeutil import now
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import CheckinCode, Reservation, Room
from app.rules import aload_rules

CHECKIN_EARLY_MINUTES = 15


def _reservation_out(row: Reservation) -> s.Reservation:
    return s.Reservation.model_validate(row, from_attributes=True)


async def get_checkin_code(session: AsyncSession, room_id: int) -> s.CheckinCodeOut:
    valid_date = now().date()
    async with session.begin():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"m1:checkin-code:{room_id}:{valid_date.isoformat()}"},
        )
        room = await session.get(Room, room_id)
        if room is None:
            raise not_found("教室", room_id)
        row = await session.get(CheckinCode, (room_id, valid_date))
        if row is None:
            row = CheckinCode(
                room_id=room_id,
                valid_date=valid_date,
                code=f"{secrets.randbelow(1_000_000):06d}",
            )
            session.add(row)
            await session.flush()
    return s.CheckinCodeOut(
        room_id=room_id,
        code=row.code,
        qr_payload=f"campus://checkin/{room_id}/{row.code}",
        valid_date=valid_date,
    )


def _checkin_open(reservation: Reservation, at: datetime, auto_cancel_min: int) -> bool:
    earliest = reservation.start_at - timedelta(minutes=CHECKIN_EARLY_MINUTES)
    latest = reservation.start_at + timedelta(minutes=auto_cancel_min)
    return earliest <= at < latest


async def check_in(
    session: AsyncSession,
    user: CurrentUser,
    reservation_id: int,
    code: str,
) -> s.Reservation:
    async with session.begin():
        reservation = await session.scalar(
            select(Reservation).where(Reservation.id == reservation_id).with_for_update()
        )
        if reservation is None or reservation.user_id != user.id:
            raise not_found("预约", reservation_id)
        if reservation.status != "booked":
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "当前预约状态不能签到")

        at = now()
        rules = await aload_rules(session)
        if not _checkin_open(reservation, at, rules.auto_cancel_min):
            raise AppError(400, "CHECKIN_WINDOW_CLOSED", "当前不在签到时间内")

        valid_date = reservation.start_at.date()
        valid_code = await session.get(CheckinCode, (reservation.room_id, valid_date))
        if valid_code is None or not hmac.compare_digest(valid_code.code, code):
            raise AppError(400, "CHECKIN_CODE_INVALID", "签到码错误")

        reservation.status = "checked_in"
        reservation.checked_in_at = at
        await session.flush()
    return _reservation_out(reservation)
