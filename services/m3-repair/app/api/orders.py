"""报修人：上报、查询、取消、验收。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from fastapi import APIRouter, Depends

from app import clients, stubs
from app import schemas as s

router = APIRouter(prefix="/api/v1/repair", tags=["报修"], responses=ERROR_RESPONSES)

Reporter = CurrentUser


@router.post("/orders", summary="上报故障", response_model=s.WorkOrder, status_code=201)
async def report(body: s.OrderCreate, user: Reporter = Depends(require_perm("repair:report"))):
    """校验 room_id（调用 M1）与 category（取自配置）。通知拥有 repair:dispatch 的调度员。"""
    await clients.get_room(body.room_id)
    return stubs.order(user)


@router.get("/orders/mine", summary="我上报的工单", response_model=Page[s.WorkOrder])
async def mine(
    status: s.OrderStatus | None = None,
    user: Reporter = Depends(require_perm("repair:report")),
    p: PageParams = Depends(page_params),
):
    return page_of([stubs.order(user)], 1, p)


@router.get("/orders/{order_id}", summary="工单详情（含时间线）", response_model=s.WorkOrder)
async def detail(
    order_id: int,
    user: Reporter = Depends(require_perm("repair:report", "repair:dispatch", "repair:work")),
):
    return stubs.order(user, order_id)


@router.post("/orders/{order_id}/cancel", summary="取消工单（仅派单前）", response_model=s.WorkOrder)
async def cancel(
    order_id: int, body: s.CancelRequest, user: Reporter = Depends(require_perm("repair:report"))
):
    """只有 submitted 状态可取消，否则 409 ORDER_STATE_CONFLICT。"""
    return stubs.order(user, order_id, status="cancelled")


@router.post("/orders/{order_id}/accept", summary="验收通过并评价", response_model=s.WorkOrder)
async def accept(
    order_id: int,
    body: s.AcceptRequest,
    user: Reporter = Depends(require_perm("repair:report", "repair:manage")),
):
    """pending_acceptance → closed。报修人本人验收；超过 admin_accept_after_hours 后
    repair:manage 可代验收。若曾下架教室，调用 M1 释放，成功后才关闭工单。"""
    order = stubs.order(user, order_id, status="closed", blocks_room=True)
    if order.blocks_room:
        await clients.release_room(order_id)
    return order


@router.post("/orders/{order_id}/reject-acceptance", summary="验收不通过", response_model=s.WorkOrder)
async def reject_acceptance(
    order_id: int,
    body: s.RejectAcceptanceRequest,
    user: Reporter = Depends(require_perm("repair:report")),
):
    """pending_acceptance → in_progress，教室保持下架。"""
    return stubs.order(user, order_id, status="in_progress")
