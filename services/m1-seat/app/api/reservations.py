"""个人预约、签到、违约记录。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from fastapi import APIRouter, Depends

from app import schemas as s
from app import stubs

router = APIRouter(prefix="/api/v1/seat", tags=["预约与签到"], responses=ERROR_RESPONSES)

Student = CurrentUser


@router.post("/reservations", summary="预约座位", response_model=s.Reservation, status_code=201)
async def create_reservation(
    body: s.ReservationCreate, user: Student = Depends(require_perm("seat:reserve"))
):
    """校验：整点、时长不超过 max_hours、在开放时间内、院系准入、座位与本人时段均无冲突、
    无 M2/M3 占用。冲突返回 409 SEAT_NOT_AVAILABLE / USER_TIME_CONFLICT。"""
    return stubs.reservation(user.id)


@router.get("/reservations/mine", summary="我的预约历史", response_model=Page[s.ReservationDetail])
async def my_reservations(
    status: s.ReservationStatus | None = None,
    user: Student = Depends(require_perm("seat:reserve")),
    p: PageParams = Depends(page_params),
):
    return page_of([stubs.reservation_detail(user.id)], 1, p)


@router.post("/reservations/{reservation_id}/cancel", summary="取消预约", response_model=s.Reservation)
async def cancel_reservation(reservation_id: int, user: Student = Depends(require_perm("seat:reserve"))):
    return stubs.reservation(user.id, reservation_id, status="cancelled")


@router.post(
    "/reservations/{reservation_id}/rebook",
    summary="按历史预约再次预约同一座位",
    response_model=s.Reservation,
    status_code=201,
)
async def rebook(
    reservation_id: int, body: s.HourRange, user: Student = Depends(require_perm("seat:reserve"))
):
    return stubs.reservation(user.id, reservation_id + 1)


@router.post("/reservations/{reservation_id}/check-in", summary="签到", response_model=s.Reservation)
async def check_in(
    reservation_id: int, body: s.CheckInRequest, user: Student = Depends(require_perm("seat:reserve"))
):
    """签到窗口：开始前 15 分钟至开始后 auto_cancel_min 分钟。签到码错误返回 400 CHECKIN_CODE_INVALID。"""
    return stubs.reservation(user.id, reservation_id, status="checked_in")


@router.get("/violations/mine", summary="我的违约记录", response_model=Page[s.ViolationOut])
async def my_violations(
    user: Student = Depends(require_perm("seat:reserve")), p: PageParams = Depends(page_params)
):
    return page_of([], 0, p)
