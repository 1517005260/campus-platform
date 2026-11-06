"""每日签到码与预约签到。"""

import hmac
import secrets
from datetime import date, datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.timeutil import now, to_biz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import CheckinCode, Reservation, Room
from app.rules import aload_rules
from app.shared import own_reservation

CHECKIN_EARLY_MINUTES = 15


def _code_date(at: datetime) -> date:
    """某一时刻教室屏幕显示的签到码所属的日期（业务时区）。签到时校验的也是这一天的码。"""
    return to_biz(at).date()


async def get_checkin_code(session: AsyncSession, room_id: int) -> s.CheckinCodeOut:
    """当天的签到码，首次请求时生成；并发的首次请求由主键 (room_id, valid_date) 保证只生成一个。"""
    valid_date = _code_date(now())
    async with session.begin():
        if await session.scalar(select(Room.id).where(Room.id == room_id)) is None:
            raise not_found("教室", room_id)
        await session.execute(
            insert(CheckinCode)
            .values(room_id=room_id, valid_date=valid_date, code=f"{secrets.randbelow(1_000_000):06d}")
            .on_conflict_do_nothing()
        )
        code = await session.scalar(
            select(CheckinCode.code).where(
                CheckinCode.room_id == room_id, CheckinCode.valid_date == valid_date
            )
        )
        rules = await aload_rules(session)
    return s.CheckinCodeOut(
        room_id=room_id,
        code=code,
        qr_payload=f"campus://checkin/{room_id}/{code}",
        valid_date=valid_date,
        early_minutes=CHECKIN_EARLY_MINUTES,
        auto_cancel_min=rules.auto_cancel_min,
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
        reservation = await own_reservation(session, user, reservation_id, for_update=True)
        if reservation.status != "booked":
            raise AppError(409, "RESERVATION_STATE_CONFLICT", "当前预约状态不能签到")

        at = now()
        rules = await aload_rules(session)
        if not _checkin_open(reservation, at, rules.auto_cancel_min):
            raise AppError(400, "CHECKIN_WINDOW_CLOSED", "当前不在签到时间内")

        valid_code = await session.get(CheckinCode, (reservation.room_id, _code_date(at)))
        if valid_code is None or not hmac.compare_digest(valid_code.code, code):
            raise AppError(400, "CHECKIN_CODE_INVALID", "签到码错误")

        reservation.status = "checked_in"
        reservation.checked_in_at = at
        await session.flush()
    return s.Reservation.model_validate(reservation, from_attributes=True)
