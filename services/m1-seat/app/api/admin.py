"""系统参数与运营统计。"""

from datetime import date

from campus_common.auth import require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.params import asave_params
from fastapi import APIRouter, Depends

from app import schemas as s
from app import stats_service
from app.models import Setting
from app.rules import aload_rules

router = APIRouter(prefix="/api/v1/seat", tags=["参数与统计"], responses=ERROR_RESPONSES)


@router.get("/settings", summary="查看预约参数", response_model=s.SeatSettings)
async def get_settings(
    session: SessionDep,
    user=Depends(require_perm("seat:config", "seat:reserve")),
):
    return await aload_rules(session)


@router.put("/settings", summary="修改预约参数", response_model=s.SeatSettings)
async def put_settings(
    body: s.SeatSettings,
    session: SessionDep,
    user=Depends(require_perm("seat:config")),
):
    """`remind_late_min` 必须小于 `auto_cancel_min`，否则 422 `VALIDATION_ERROR`。"""
    async with session.begin():
        await asave_params(session, Setting, body)
    return body


@router.get("/stats/usage", summary="座位利用率与违约率", response_model=s.UsageStats)
async def usage_stats(
    date_from: date,
    date_to: date,
    session: SessionDep,
    room_id: int | None = None,
    user=Depends(require_perm("seat:stats")),
):
    """利用率与违约率口径见 ADR-012。

    `date_to` 早于 `date_from`：400 `INVALID_DATE_RANGE`；教室不存在：404 `NOT_FOUND`。"""
    return await stats_service.usage_stats(
        session,
        date_from=date_from,
        date_to=date_to,
        room_id=room_id,
    )
