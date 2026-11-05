"""调度员与维修工：工单列表、派单、开始维修、完工；报修配置。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends

from app import orders
from app import schemas as s

router = APIRouter(prefix="/api/v1/repair", tags=["派单与维修"], responses=ERROR_RESPONSES)


@router.get("/orders", summary="工单列表（调度、维修工、管理）", response_model=Page[s.WorkOrder])
async def list_orders(
    session: SessionDep,
    status: s.OrderStatus | None = None,
    room_id: int | None = None,
    assignee_id: int | None = None,
    escalated: bool | None = None,
    user: CurrentUser = Depends(require_perm("repair:dispatch", "repair:work", "repair:manage")),
    p: PageParams = Depends(page_params),
):
    """新的在前。只有 repair:work 的用户只能看到派给自己的工单。"""
    return await orders.list_orders(
        session,
        user,
        status=status,
        room_id=room_id,
        assignee_id=assignee_id,
        escalated=escalated,
        params=p,
    )


@router.post("/orders/{order_id}/dispatch", summary="派单", response_model=s.WorkOrder)
async def dispatch(
    order_id: int,
    body: s.DispatchRequest,
    session: SessionDep,
    user: CurrentUser = Depends(require_perm("repair:dispatch")),
):
    """submitted → dispatched，通知维修工。assignee 必须拥有 repair:work（调用 common 校验）。

    错误：400 `DEADLINE_NOT_FUTURE`（截止时间不晚于现在）、400 `ASSIGNEE_NOT_WORKER`、
    404 `NOT_FOUND`、409 `ORDER_STATE_CONFLICT`（不在 submitted）、
    502 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_ERROR`（common 不可达或拒绝调用）。"""
    return await orders.dispatch(session, user, order_id, body)


@router.post("/orders/{order_id}/start", summary="开始维修", response_model=s.WorkOrder)
async def start(
    order_id: int,
    session: SessionDep,
    user: CurrentUser = Depends(require_perm("repair:work")),
):
    """dispatched → in_progress，通知报修人。blocks_room=true 时先调用 M1 下架教室，成功后才改状态；
    下架起点在首次尝试时固定，重试发出相同的请求（幂等键 m3-order-{id}-block）。

    错误：404 `NOT_FOUND`（看不到该工单）、403 `NOT_ASSIGNEE`（看得到但不是被指派人）、
    409 `ORDER_STATE_CONFLICT`（不在 dispatched）、
    502 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_ERROR`（M1 失败，工单保持 dispatched）；M1 的业务错误原样返回。"""
    return await orders.start(session, user, order_id)


@router.post("/orders/{order_id}/complete", summary="完工", response_model=s.WorkOrder)
async def complete(
    order_id: int,
    body: s.CompleteRequest,
    session: SessionDep,
    user: CurrentUser = Depends(require_perm("repair:work")),
):
    """in_progress → pending_acceptance。教室在验收通过前保持下架。通知报修人验收。

    错误：404 `NOT_FOUND`（看不到该工单）、403 `NOT_ASSIGNEE`、
    409 `ORDER_STATE_CONFLICT`（不在 in_progress）。"""
    return await orders.complete(session, user, order_id, body)


@router.get("/settings", summary="报修配置", response_model=s.RepairSettings)
async def get_settings(
    session: SessionDep,
    user=Depends(require_perm("repair:manage", "repair:report")),
):
    return await orders.get_settings(session)


@router.put("/settings", summary="更新报修配置", response_model=s.RepairSettings)
async def put_settings(
    body: s.RepairSettings,
    session: SessionDep,
    user=Depends(require_perm("repair:manage")),
):
    return await orders.put_settings(session, body)
