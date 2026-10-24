"""系统参数与运营统计。"""

from datetime import date

from campus_common.auth import require_perm
from campus_common.errors import ERROR_RESPONSES
from fastapi import APIRouter, Depends

from app import schemas as s
from app import stubs

router = APIRouter(prefix="/api/v1/seat", tags=["参数与统计"], responses=ERROR_RESPONSES)


@router.get("/settings", summary="查看预约参数", response_model=s.SeatSettings)
async def get_settings(user=Depends(require_perm("seat:config", "seat:reserve"))):
    return s.SeatSettings()


@router.put("/settings", summary="修改预约参数", response_model=s.SeatSettings)
async def put_settings(body: s.SeatSettings, user=Depends(require_perm("seat:config"))):
    return body


@router.get("/stats/usage", summary="座位利用率与违约率", response_model=s.UsageStats)
async def usage_stats(
    date_from: date,
    date_to: date,
    room_id: int | None = None,
    user=Depends(require_perm("seat:stats")),
):
    return stubs.usage()
