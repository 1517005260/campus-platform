"""自习室与座位：主数据维护、搜索、可用性、签到码、状态追溯。"""

from datetime import date
from typing import Annotated

from campus_common.auth import CurrentUser, CurrentUserDep, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from campus_common.query import query_model
from fastapi import APIRouter, Depends, Query

from app import availability, checkin_service, room_service
from app import schemas as s

router = APIRouter(prefix="/api/v1/seat", tags=["自习室与座位"], responses=ERROR_RESPONSES)


@router.get("/rooms", summary="查询自习室列表", response_model=Page[s.Room])
async def list_rooms(
    user: CurrentUserDep,
    session: SessionDep,
    building: str | None = Query(None, description="楼宇名称"),
    type: s.RoomType | None = None,
    is_study_room: bool | None = None,
    is_whole_bookable: bool | None = Query(None, description="M2 申请选教室时传 true"),
    p: PageParams = Depends(page_params),
):
    """院系自习室只对本院系用户可见（按 token 中的 dept_id 过滤）；
    `seat:checkin_code` 可见所有院系的启用教室；`seat:room_manage`、`seat:stats` 可见全部教室（含停用）。
    详情、可用性的可见性相同。"""
    return await room_service.list_rooms(
        session,
        user,
        building=building,
        type=type,
        is_study_room=is_study_room,
        is_whole_bookable=is_whole_bookable,
        params=p,
    )


@router.get("/rooms/{room_id}", summary="自习室详情（含座位）", response_model=s.RoomDetail)
async def get_room(room_id: int, user: CurrentUserDep, session: SessionDep):
    """教室不存在或对当前用户不可见：404 `NOT_FOUND`。"""
    return await room_service.get_room(session, user, room_id)


@router.post("/rooms", summary="登记自习室", response_model=s.Room, status_code=201)
async def create_room(
    body: s.RoomCreate, session: SessionDep, user=Depends(require_perm("seat:room_manage"))
):
    """同一星期配置多条开放时间：400 `INVALID_OPEN_HOURS`；同一楼宇重名：409 `ROOM_ALREADY_EXISTS`。"""
    return await room_service.create_room(session, body)


@router.patch("/rooms/{room_id}", summary="修改自习室（含开放时间、启用/停用）", response_model=s.Room)
async def update_room(
    room_id: int,
    body: s.RoomUpdate,
    session: SessionDep,
    user=Depends(require_perm("seat:room_manage")),
):
    """停用教室或注销自习室（`is_study_room` 由 true 改为 false）时，该教室尚未结束的有效预约全部取消
    （`cancel_reason=ADMIN_DISABLED`，不记违约，通知学生）。

    错误：404 `NOT_FOUND`；400 `INVALID_OPEN_HOURS`；409 `ROOM_ALREADY_EXISTS`。"""
    return await room_service.update_room(session, room_id, body)


@router.post("/rooms/{room_id}/seats", summary="登记座位", response_model=s.Seat, status_code=201)
async def create_seat(
    room_id: int,
    body: s.SeatCreate,
    session: SessionDep,
    user=Depends(require_perm("seat:room_manage")),
):
    """教室不存在：404 `NOT_FOUND`；同一教室座位编号重复：409 `SEAT_ALREADY_EXISTS`。"""
    return await room_service.create_seat(session, room_id, body)


@router.patch("/seats/{seat_id}", summary="修改座位（插座标记、启用/停用）", response_model=s.Seat)
async def update_seat(
    seat_id: int,
    body: s.SeatUpdate,
    session: SessionDep,
    user=Depends(require_perm("seat:room_manage")),
):
    """停用座位时，该座位尚未结束的有效预约全部取消（`cancel_reason=ADMIN_DISABLED`，不记违约，通知学生）。

    座位不存在：404 `NOT_FOUND`。"""
    return await room_service.update_seat(session, seat_id, body)


@router.get("/seats/search", summary="按条件搜索可预约座位", response_model=Page[s.SeatSearchItem])
async def search_seats(
    user: CurrentUserDep,
    session: SessionDep,
    slot: Annotated[s.HourRange, Depends(query_model(s.HourRange))],
    building: str | None = None,
    room_id: int | None = None,
    outlet: s.Outlet | None = Query(None, description="按插座条件筛选"),
    p: PageParams = Depends(page_params),
):
    """只返回当前用户在该时段真正可约的座位，规则与创建预约相同：座位与教室启用、院系允许、
    在开放时间内、无有效预约、无 M2/M3 占用。

    时段本身不可约时与创建预约返回同样的错误：结束不晚于开始 422 `VALIDATION_ERROR`；
    时段已开始 400 `RESERVATION_IN_PAST`；超过 `max_hours` 400 `INVALID_DURATION`。"""
    return await availability.search_seats(
        session,
        user,
        slot=slot,
        building=building,
        room_id=room_id,
        outlet=outlet,
        params=p,
    )


@router.get(
    "/rooms/{room_id}/availability",
    summary="某天各座位按小时的状态",
    response_model=list[s.SeatAvailability],
)
async def room_availability(room_id: int, date: date, user: CurrentUserDep, session: SessionDep):
    """每个座位每个整点：closed（不在开放时间）、
    blocked（`M1_ADMIN` 停用或 `M2_OCCUPY`/`M3_MAINTENANCE` 占用）、reserved（有效预约）、free。
    教室不存在或不可见：404 `NOT_FOUND`。"""
    return await availability.room_availability(session, user, room_id, date)


@router.get(
    "/rooms/{room_id}/checkin-code", summary="当日签到码（教室屏幕用）", response_model=s.CheckinCodeOut
)
async def get_checkin_code(
    room_id: int,
    session: SessionDep,
    user=Depends(require_perm("seat:checkin_code")),
):
    """业务日期当天的签到码，当天首次请求时生成。
    附签到窗口：预约开始前 `early_minutes` 分钟至开始后 `auto_cancel_min` 分钟（与签到接口同一组参数）。

    教室不存在：404 `NOT_FOUND`。"""
    return await checkin_service.get_checkin_code(session, room_id)


@router.get(
    "/seats/{seat_id}/status-history",
    summary="座位状态变化及写入来源",
    response_model=list[s.StatusHistoryItem],
)
async def seat_status_history(
    seat_id: int,
    session: SessionDep,
    user: CurrentUser = Depends(require_perm("seat:room_manage", "seat:stats")),
):
    """座位不存在：404 `NOT_FOUND`。"""
    return await availability.status_history(session, seat_id)
