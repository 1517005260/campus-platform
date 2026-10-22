"""自习室与座位：主数据维护、搜索、可用性、签到码、状态追溯。"""

from datetime import date

from campus_common.auth import CurrentUser, CurrentUserDep, require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from fastapi import APIRouter, Depends, Query

from app import schemas as s
from app import stubs

router = APIRouter(prefix="/api/v1/seat", tags=["自习室与座位"], responses=ERROR_RESPONSES)


@router.get("/rooms", summary="查询自习室列表", response_model=Page[s.Room])
async def list_rooms(
    user: CurrentUserDep,
    building: str | None = Query(None, description="楼宇名称"),
    type: s.RoomType | None = None,
    is_study_room: bool | None = None,
    is_whole_bookable: bool | None = Query(None, description="M2 申请选教室时传 true"),
    p: PageParams = Depends(page_params),
):
    """院系自习室只对本院系用户可见（按 token 中的 dept_id 过滤）。"""
    return page_of([stubs.ROOM], 1, p)


@router.get("/rooms/{room_id}", summary="自习室详情（含座位）", response_model=s.RoomDetail)
async def get_room(room_id: int, user: CurrentUserDep):
    return s.RoomDetail(**stubs.ROOM.model_dump(), seats=stubs.SEATS)


@router.post("/rooms", summary="登记自习室", response_model=s.Room, status_code=201)
async def create_room(body: s.RoomCreate, user=Depends(require_perm("seat:room_manage"))):
    return stubs.ROOM


@router.patch("/rooms/{room_id}", summary="修改自习室（含开放时间、启用/停用）", response_model=s.Room)
async def update_room(room_id: int, body: s.RoomUpdate, user=Depends(require_perm("seat:room_manage"))):
    return stubs.ROOM


@router.post("/rooms/{room_id}/seats", summary="登记座位", response_model=s.Seat, status_code=201)
async def create_seat(room_id: int, body: s.SeatCreate, user=Depends(require_perm("seat:room_manage"))):
    return stubs.SEATS[0]


@router.patch("/seats/{seat_id}", summary="修改座位（插座标记、启用/停用）", response_model=s.Seat)
async def update_seat(seat_id: int, body: s.SeatUpdate, user=Depends(require_perm("seat:room_manage"))):
    return stubs.SEATS[0]


@router.get("/seats/search", summary="按条件搜索可预约座位", response_model=Page[s.SeatSearchItem])
async def search_seats(
    user: CurrentUserDep,
    date: date,
    start_hour: int = Query(ge=0, le=23),
    end_hour: int = Query(ge=1, le=24),
    building: str | None = None,
    room_id: int | None = None,
    outlet: s.Outlet | None = Query(None, description="按插座条件筛选"),
    p: PageParams = Depends(page_params),
):
    """只返回该时段真正可约的座位：座位启用、在开放时间内、无有效预约、无 M2/M3 占用。"""
    items = [s.SeatSearchItem(seat=seat, room=stubs.ROOM) for seat in stubs.SEATS]
    return page_of(items, len(items), p)


@router.get(
    "/rooms/{room_id}/availability",
    summary="某天各座位按小时的状态",
    response_model=list[s.SeatAvailability],
)
async def room_availability(room_id: int, date: date, user: CurrentUserDep):
    return stubs.availability()


@router.get(
    "/rooms/{room_id}/checkin-code", summary="当日签到码（教室屏幕用）", response_model=s.CheckinCodeOut
)
async def get_checkin_code(room_id: int, user=Depends(require_perm("seat:checkin_code"))):
    return stubs.checkin_code(room_id)


@router.get(
    "/seats/{seat_id}/status-history",
    summary="座位状态变化及写入来源",
    response_model=list[s.StatusHistoryItem],
)
async def seat_status_history(
    seat_id: int,
    user: CurrentUser = Depends(require_perm("seat:room_manage", "seat:stats")),
):
    return stubs.status_history()
