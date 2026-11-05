"""个人预约、签到、违约记录。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends

from app import checkin_service, reservation_service
from app import schemas as s

router = APIRouter(prefix="/api/v1/seat", tags=["预约与签到"], responses=ERROR_RESPONSES)

Student = CurrentUser


@router.post("/reservations", summary="预约座位", response_model=s.Reservation, status_code=201)
async def create_reservation(
    body: s.ReservationCreate,
    session: SessionDep,
    user: Student = Depends(require_perm("seat:reserve")),
):
    """校验与座位搜索使用同一组规则。错误：
    422 `VALIDATION_ERROR`（结束不晚于开始）；
    400 `RESERVATION_IN_PAST`、`INVALID_DURATION`（超过 `max_hours`）、`OUTSIDE_OPEN_HOURS`；
    404 `NOT_FOUND`（座位不存在）；403 `DEPT_RESTRICTED`；
    409 `SEAT_NOT_AVAILABLE`（座位或教室停用、被预约、被 M2/M3 占用）、`USER_TIME_CONFLICT`。"""
    return await reservation_service.create_reservation(session, user, body.seat_id, body)


@router.get("/reservations/mine", summary="我的预约历史", response_model=Page[s.ReservationDetail])
async def my_reservations(
    session: SessionDep,
    status: s.ReservationStatus | None = None,
    user: Student = Depends(require_perm("seat:reserve")),
    p: PageParams = Depends(page_params),
):
    return await reservation_service.my_reservations(session, user, status=status, params=p)


@router.post("/reservations/{reservation_id}/cancel", summary="取消预约", response_model=s.Reservation)
async def cancel_reservation(
    reservation_id: int,
    session: SessionDep,
    user: Student = Depends(require_perm("seat:reserve")),
):
    """只能取消自己未开始的 booked 预约。不是本人的预约：404 `NOT_FOUND`；其他状态或已开始：
    409 `RESERVATION_STATE_CONFLICT`。"""
    return await reservation_service.cancel_reservation(session, user, reservation_id)


@router.post(
    "/reservations/{reservation_id}/rebook",
    summary="按历史预约再次预约同一座位",
    response_model=s.Reservation,
    status_code=201,
)
async def rebook(
    reservation_id: int,
    body: s.HourRange,
    session: SessionDep,
    user: Student = Depends(require_perm("seat:reserve")),
):
    """为历史预约的同一座位预约新时段。历史预约不是本人的：404 `NOT_FOUND`；其余错误同"预约座位"。"""
    return await reservation_service.rebook(session, user, reservation_id, body)


@router.post("/reservations/{reservation_id}/check-in", summary="签到", response_model=s.Reservation)
async def check_in(
    reservation_id: int,
    body: s.CheckInRequest,
    session: SessionDep,
    user: Student = Depends(require_perm("seat:reserve")),
):
    """签到窗口：开始前 15 分钟至开始后 `auto_cancel_min` 分钟之前；签到码为教室屏幕当前显示的当天的码。

    错误：404 `NOT_FOUND`（不是本人的预约）；409 `RESERVATION_STATE_CONFLICT`（不是 booked，包括已被取消）；
    400 `CHECKIN_WINDOW_CLOSED`、`CHECKIN_CODE_INVALID`。"""
    return await checkin_service.check_in(session, user, reservation_id, body.code)


@router.get("/violations/mine", summary="我的违约记录", response_model=Page[s.ViolationOut])
async def my_violations(
    session: SessionDep,
    user: Student = Depends(require_perm("seat:reserve")),
    p: PageParams = Depends(page_params),
):
    return await reservation_service.my_violations(session, user, p)
