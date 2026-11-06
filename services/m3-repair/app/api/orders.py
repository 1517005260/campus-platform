"""报修人：上报、查询、取消、验收。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends

from app import orders
from app import schemas as s

router = APIRouter(prefix="/api/v1/repair", tags=["报修"], responses=ERROR_RESPONSES)

Reporter = CurrentUser


@router.post("/orders", summary="上报故障", response_model=s.WorkOrder, status_code=201)
async def report(
    body: s.OrderCreate,
    session: SessionDep,
    user: Reporter = Depends(require_perm("repair:report")),
):
    """校验 room_id、seat_id（调用 M1）与 category（取自配置）。通知拥有 repair:dispatch 的调度员。

    错误：400 `ROOM_NOT_FOUND`（M1 中没有该教室）、400 `SEAT_NOT_IN_ROOM`（座位不存在或不属于该教室）、
    400 `UNKNOWN_CATEGORY`、
    502 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_ERROR`（M1 不可达或拒绝调用）。"""
    return await orders.report(session, user, body)


@router.get("/orders/mine", summary="我上报的工单", response_model=Page[s.WorkOrder])
async def mine(
    session: SessionDep,
    status: s.OrderStatus | None = None,
    user: Reporter = Depends(require_perm("repair:report")),
    p: PageParams = Depends(page_params),
):
    """本人上报的工单，新的在前。"""
    return await orders.list_mine(session, user, status, p)


@router.get("/orders/{order_id}", summary="工单详情（含时间线）", response_model=s.WorkOrder)
async def detail(
    order_id: int,
    session: SessionDep,
    user: Reporter = Depends(
        require_perm("repair:report", "repair:dispatch", "repair:work", "repair:manage")
    ),
):
    """报修人本人、被指派的维修工、调度与管理可见；其他人 404 `NOT_FOUND`（不暴露工单是否存在）。"""
    return await orders.detail(session, user, order_id)


@router.post("/orders/{order_id}/cancel", summary="取消工单（仅派单前）", response_model=s.WorkOrder)
async def cancel(
    order_id: int,
    body: s.CancelRequest,
    session: SessionDep,
    user: Reporter = Depends(require_perm("repair:report")),
):
    """submitted → cancelled，通知调度员不必再派单。

    错误：404 `NOT_FOUND`（看不到该工单）、403 `FORBIDDEN`（看得到但不是报修人）、
    409 `ORDER_STATE_CONFLICT`（已派单或已结束）。"""
    return await orders.cancel(session, user, order_id, body)


@router.post("/orders/{order_id}/accept", summary="验收通过并评价", response_model=s.WorkOrder)
async def accept(
    order_id: int,
    body: s.AcceptRequest,
    session: SessionDep,
    user: Reporter = Depends(require_perm("repair:report", "repair:manage")),
):
    """pending_acceptance → closed，通知维修工。报修人本人验收；完工 admin_accept_after_hours 后（含该时刻）
    repair:manage 可代验收（closed_by 记录实际操作人，时间线动作为 `admin_accept`）。
    若曾下架教室，先调用 M1 释放，成功后才关闭工单。

    错误：404 `NOT_FOUND`（看不到该工单）、409 `ORDER_STATE_CONFLICT`（不在待验收）、
    403 `ADMIN_ACCEPT_TOO_EARLY`（管理员代验收时间未到）、
    403 `FORBIDDEN`（看得到但既不是报修人也不能代验收）、
    502 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_ERROR`（M1 释放失败，工单保持待验收）。"""
    return await orders.accept(session, user, order_id, body)


@router.post("/orders/{order_id}/reject-acceptance", summary="验收不通过", response_model=s.WorkOrder)
async def reject_acceptance(
    order_id: int,
    body: s.RejectAcceptanceRequest,
    session: SessionDep,
    user: Reporter = Depends(require_perm("repair:report")),
):
    """pending_acceptance → in_progress，教室保持下架，通知维修工。

    错误：404 `NOT_FOUND`（看不到该工单）、403 `FORBIDDEN`（看得到但不是报修人）、
    409 `ORDER_STATE_CONFLICT`（不在待验收）。"""
    return await orders.reject(session, user, order_id, body)
