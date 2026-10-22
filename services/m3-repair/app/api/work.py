"""调度员与维修工：工单列表、派单、开始维修、完工；报修配置。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from campus_common.timeutil import now
from fastapi import APIRouter, Depends

from app import clients, stubs
from app import schemas as s

router = APIRouter(prefix="/api/v1/repair", tags=["派单与维修"], responses=ERROR_RESPONSES)


@router.get("/orders", summary="工单列表（调度、维修工、管理）", response_model=Page[s.WorkOrder])
async def list_orders(
    status: s.OrderStatus | None = None,
    room_id: int | None = None,
    assignee_id: int | None = None,
    escalated: bool | None = None,
    user: CurrentUser = Depends(require_perm("repair:dispatch", "repair:work", "repair:manage")),
    p: PageParams = Depends(page_params),
):
    """只有 repair:work 的用户只能看到派给自己的工单。"""
    return page_of([stubs.order(user)], 1, p)


@router.post("/orders/{order_id}/dispatch", summary="派单", response_model=s.WorkOrder)
async def dispatch(
    order_id: int,
    body: s.DispatchRequest,
    user: CurrentUser = Depends(require_perm("repair:dispatch")),
):
    """submitted → dispatched。assignee 必须拥有 repair:work。通知维修工。"""
    return stubs.order(user, order_id, status="dispatched", blocks_room=body.blocks_room)


@router.post("/orders/{order_id}/start", summary="开始维修", response_model=s.WorkOrder)
async def start(order_id: int, user: CurrentUser = Depends(require_perm("repair:work"))):
    """dispatched → in_progress。blocks_room=true 时先调用 M1 下架教室，
    成功后才改状态；M1 失败则本地不变并返回 502。"""
    order = stubs.order(user, order_id, status="in_progress", blocks_room=True)
    if order.blocks_room:
        await clients.block_room(order_id, order.room_id, now(), f"报修工单 #{order_id} 维修中")
    return order


@router.post("/orders/{order_id}/complete", summary="完工", response_model=s.WorkOrder)
async def complete(
    order_id: int, body: s.CompleteRequest, user: CurrentUser = Depends(require_perm("repair:work"))
):
    """in_progress → pending_acceptance。教室在验收通过前保持下架。通知报修人验收。"""
    return stubs.order(user, order_id, status="pending_acceptance")


@router.get("/settings", summary="报修配置", response_model=s.RepairSettings)
async def get_settings(user=Depends(require_perm("repair:manage", "repair:report"))):
    return s.RepairSettings()


@router.put("/settings", summary="更新报修配置", response_model=s.RepairSettings)
async def put_settings(body: s.RepairSettings, user=Depends(require_perm("repair:manage"))):
    return body
