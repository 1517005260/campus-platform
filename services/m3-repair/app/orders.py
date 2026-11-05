"""工单状态机。一次迁移只走这里：先检查，需要动教室时先调用 M1，成功后再提交本地状态。"""

from datetime import datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.errors import AppError
from campus_common.events import NotificationSend, Ref, WorkOrderStatusChanged
from campus_common.outbox import add_event
from campus_common.pagination import Page, PageParams, page_of
from campus_common.params import aload_params, asave_params
from campus_common.timeutil import now
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients
from app import schemas as s
from app.config import settings
from app.models import Outbox, Setting, WorkOrder, WorkOrderEvent

PRODUCER = settings.service_name


async def report(session: AsyncSession, user: CurrentUser, body: s.OrderCreate) -> s.WorkOrder:
    await _ensure_room(body.room_id)
    dispatchers = await clients.users_with_perm("repair:dispatch")
    async with session.begin():
        rules = await aload_params(session, Setting, s.RepairSettings)
        if body.category not in rules.categories:
            raise AppError(400, "UNKNOWN_CATEGORY", "分类不在配置中")
        order = WorkOrder(
            reporter_id=user.id,
            room_id=body.room_id,
            seat_id=body.seat_id,
            category=body.category,
            description=body.description,
            photos=list(body.photos),
            status="submitted",
            blocks_room=False,
            escalation_level=0,
            version=1,
        )
        session.add(order)
        await session.flush()
        _event(session, order, user.id, "report", None, "submitted", None)
        _notify(session, [person.id for person in dispatchers], "repair.reported", order.id, order.status)
        _status_changed(session, order.id, None, "submitted")
        return await _present(session, order)


async def list_mine(
    session: AsyncSession, user: CurrentUser, status: s.OrderStatus | None, params: PageParams
) -> Page[s.WorkOrder]:
    stmt = select(WorkOrder).where(WorkOrder.reporter_id == user.id)
    if status is not None:
        stmt = stmt.where(WorkOrder.status == status)
    return await _page(session, stmt, params)


async def list_orders(
    session: AsyncSession,
    user: CurrentUser,
    *,
    status: s.OrderStatus | None,
    room_id: int | None,
    assignee_id: int | None,
    escalated: bool | None,
    params: PageParams,
) -> Page[s.WorkOrder]:
    stmt = select(WorkOrder)
    if user.has("repair:work") and not user.has("repair:dispatch") and not user.has("repair:manage"):
        stmt = stmt.where(WorkOrder.assignee_id == user.id)
    if status is not None:
        stmt = stmt.where(WorkOrder.status == status)
    if room_id is not None:
        stmt = stmt.where(WorkOrder.room_id == room_id)
    if assignee_id is not None:
        stmt = stmt.where(WorkOrder.assignee_id == assignee_id)
    if escalated is True:
        stmt = stmt.where(WorkOrder.escalation_level > 0)
    elif escalated is False:
        stmt = stmt.where(WorkOrder.escalation_level == 0)
    return await _page(session, stmt, params)


async def detail(session: AsyncSession, user: CurrentUser, order_id: int) -> s.WorkOrder:
    order = await _visible(session, user, order_id)
    return await _present(session, order)


async def cancel(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.CancelRequest
) -> s.WorkOrder:
    async with session.begin():
        order = await _visible(session, user, order_id, lock=True)
        if order.reporter_id != user.id:
            raise AppError(403, "FORBIDDEN", "只有报修人可以取消")
        if order.status != "submitted":
            raise _conflict(order)
        previous = order.status
        order.status = "cancelled"
        _event(session, order, user.id, "cancel", previous, "cancelled", body.reason)
        _notify(session, [order.reporter_id], "repair.cancelled", order.id, order.status)
        _status_changed(session, order.id, previous, "cancelled")
        return await _present(session, order)


async def dispatch(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.DispatchRequest
) -> s.WorkOrder:
    if body.deadline_at <= now():
        raise AppError(400, "DEADLINE_NOT_FUTURE", "截止时间必须晚于现在")
    workers = await clients.users_with_perm("repair:work")
    if body.assignee_id not in {person.id for person in workers}:
        raise AppError(400, "ASSIGNEE_NOT_WORKER", "派单对象没有维修权限")
    async with session.begin():
        order = await _lock(session, order_id)
        if order.status != "submitted":
            raise _conflict(order)
        previous = order.status
        order.status = "dispatched"
        order.assignee_id = body.assignee_id
        order.deadline_at = body.deadline_at
        order.blocks_room = body.blocks_room
        _event(session, order, user.id, "dispatch", previous, "dispatched", None)
        _notify(session, [body.assignee_id], "repair.dispatched", order.id, order.status)
        _status_changed(session, order.id, previous, "dispatched")
        return await _present(session, order)


async def start(session: AsyncSession, user: CurrentUser, order_id: int) -> s.WorkOrder:
    preview = await _lock_preview(session, order_id)
    if preview.assignee_id != user.id:
        raise AppError(403, "NOT_ASSIGNEE", "只有被指派的维修工可以操作")
    if preview.status != "dispatched":
        raise _conflict(preview)
    if preview.blocks_room:
        await clients.block_room(order_id, preview.room_id, now(), f"报修工单 #{order_id} 维修中")
    async with session.begin():
        order = await _lock(session, order_id)
        if order.assignee_id != user.id:
            raise AppError(403, "NOT_ASSIGNEE", "只有被指派的维修工可以操作")
        if order.status != "dispatched":
            raise _conflict(order)
        previous = order.status
        order.status = "in_progress"
        _event(session, order, user.id, "start", previous, "in_progress", None)
        _notify(session, [order.reporter_id], "repair.started", order.id, order.status)
        _status_changed(session, order.id, previous, "in_progress")
        return await _present(session, order)


async def complete(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.CompleteRequest
) -> s.WorkOrder:
    async with session.begin():
        order = await _lock(session, order_id)
        if order.assignee_id != user.id:
            raise AppError(403, "NOT_ASSIGNEE", "只有被指派的维修工可以操作")
        if order.status != "in_progress":
            raise _conflict(order)
        previous = order.status
        order.status = "pending_acceptance"
        order.completed_at = now()
        if body.photos:
            order.photos = [*order.photos, *body.photos]
        _event(session, order, user.id, "complete", previous, "pending_acceptance", body.note)
        _notify(session, [order.reporter_id], "repair.completed", order.id, order.status)
        _status_changed(session, order.id, previous, "pending_acceptance")
        return await _present(session, order)


async def accept(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.AcceptRequest
) -> s.WorkOrder:
    preview, rules = await _preview(session, order_id)
    _require_acceptor(user, preview, _deadline(preview, rules))
    if preview.blocks_room:
        await clients.release_room(order_id)
    async with session.begin():
        order = await _lock(session, order_id)
        rules = await aload_params(session, Setting, s.RepairSettings)
        _require_acceptor(user, order, _deadline(order, rules))
        previous = order.status
        order.status = "closed"
        order.rating = body.rating
        order.rating_comment = body.comment
        order.closed_by = user.id
        _event(session, order, user.id, "accept", previous, "closed", body.comment)
        _notify(
            session,
            [order.assignee_id] if order.assignee_id else [],
            "repair.accepted",
            order.id,
            order.status,
        )
        _status_changed(session, order.id, previous, "closed")
        return await _present(session, order)


async def reject(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.RejectAcceptanceRequest
) -> s.WorkOrder:
    async with session.begin():
        order = await _visible(session, user, order_id, lock=True)
        if order.reporter_id != user.id:
            raise AppError(403, "FORBIDDEN", "只有报修人可以拒绝验收")
        if order.status != "pending_acceptance":
            raise _conflict(order)
        previous = order.status
        order.status = "in_progress"
        _event(session, order, user.id, "reject", previous, "in_progress", body.reason)
        targets = [order.assignee_id] if order.assignee_id else []
        _notify(session, targets, "repair.rejected", order.id, order.status)
        _status_changed(session, order.id, previous, "in_progress")
        return await _present(session, order)


async def get_settings(session: AsyncSession) -> s.RepairSettings:
    return await aload_params(session, Setting, s.RepairSettings)


async def put_settings(session: AsyncSession, body: s.RepairSettings) -> s.RepairSettings:
    async with session.begin():
        await asave_params(session, Setting, body)
    return body


async def _ensure_room(room_id: int) -> None:
    try:
        await clients.get_room(room_id)
    except AppError as exc:
        if exc.status == 404 and exc.code == "NOT_FOUND":
            raise AppError(400, "ROOM_NOT_FOUND", "教室不存在") from exc
        raise


async def _preview(session: AsyncSession, order_id: int) -> tuple[WorkOrder, s.RepairSettings]:
    async with session.begin():
        return await _lock(session, order_id), await aload_params(session, Setting, s.RepairSettings)


def _deadline(order: WorkOrder, rules: s.RepairSettings) -> datetime | None:
    if order.completed_at is None:
        return None
    return order.completed_at + timedelta(hours=rules.admin_accept_after_hours)


def _require_acceptor(user: CurrentUser, order: WorkOrder, deadline: datetime | None) -> None:
    if order.status != "pending_acceptance":
        raise _conflict(order)
    if order.reporter_id == user.id and user.has("repair:report"):
        return
    if user.has("repair:manage"):
        if deadline is None or now() < deadline:
            raise AppError(403, "ADMIN_ACCEPT_TOO_EARLY", "未到管理员代验收时间")
        return
    raise AppError(403, "FORBIDDEN", "只有报修人或到时代验收的管理员可以验收")


async def _page(session: AsyncSession, stmt, params: PageParams) -> Page[s.WorkOrder]:
    ordered = stmt.order_by(WorkOrder.id.desc())
    total = await session.scalar(select(func.count()).select_from(ordered.order_by(None).subquery()))
    rows = (await session.scalars(ordered.offset(params.offset).limit(params.size))).all()
    items = [await _present(session, order) for order in rows]
    return page_of(items, total or 0, params)


async def _lock_preview(session: AsyncSession, order_id: int) -> WorkOrder:
    """读出并结束当前事务，便于在调用 M1 期间不占着行锁。"""
    async with session.begin():
        return await _lock(session, order_id)


async def _visible(
    session: AsyncSession, user: CurrentUser, order_id: int, *, lock: bool = False
) -> WorkOrder:
    order = await _lock(session, order_id) if lock else await _get(session, order_id)
    if not _can_view(order, user):
        raise AppError(404, "NOT_FOUND", f"工单 {order_id} 不存在")
    return order


async def _get(session: AsyncSession, order_id: int) -> WorkOrder:
    order = await session.get(WorkOrder, order_id)
    if order is None:
        raise AppError(404, "NOT_FOUND", f"工单 {order_id} 不存在")
    return order


async def _lock(session: AsyncSession, order_id: int) -> WorkOrder:
    order = await session.get(WorkOrder, order_id, with_for_update=True)
    if order is None:
        raise AppError(404, "NOT_FOUND", f"工单 {order_id} 不存在")
    return order


def _can_view(order: WorkOrder, user: CurrentUser) -> bool:
    if user.has("repair:dispatch") or user.has("repair:manage"):
        return True
    if user.has("repair:report") and order.reporter_id == user.id:
        return True
    return bool(user.has("repair:work") and order.assignee_id == user.id)


def _conflict(order: WorkOrder) -> AppError:
    return AppError(409, "ORDER_STATE_CONFLICT", f"当前状态为 {order.status}，不能执行此操作")


def _event(
    session: AsyncSession,
    order: WorkOrder,
    actor_id: int | None,
    action: str,
    from_status: str | None,
    to_status: str | None,
    note: str | None,
) -> None:
    session.add(
        WorkOrderEvent(
            order_id=order.id,
            at=now(),
            actor_id=actor_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            note=note,
        )
    )


def _notify(session: AsyncSession, user_ids: list[int], template: str, order_id: int, status: str) -> None:
    ids = [user_id for user_id in user_ids if user_id is not None]
    if not ids:
        return
    add_event(
        session,
        Outbox,
        PRODUCER,
        NotificationSend(
            user_ids=ids,
            template=template,
            params={"order_id": order_id, "status": status},
            ref=Ref(module="m3", type="work_order", id=order_id),
        ),
    )


def _status_changed(session: AsyncSession, order_id: int, from_status: str | None, to_status: str) -> None:
    add_event(
        session,
        Outbox,
        PRODUCER,
        WorkOrderStatusChanged(order_id=order_id, from_status=from_status or "", to_status=to_status),
    )


async def _present(session: AsyncSession, order: WorkOrder) -> s.WorkOrder:
    events = (
        await session.scalars(
            select(WorkOrderEvent).where(WorkOrderEvent.order_id == order.id).order_by(WorkOrderEvent.id)
        )
    ).all()
    ids = {order.reporter_id, *(event.actor_id for event in events if event.actor_id is not None)}
    if order.assignee_id is not None:
        ids.add(order.assignee_id)
    people = {user_id: await _brief(user_id) for user_id in ids}
    return s.WorkOrder(
        id=order.id,
        reporter=people[order.reporter_id],
        room_id=order.room_id,
        seat_id=order.seat_id,
        category=order.category,
        description=order.description,
        photos=list(order.photos),
        status=order.status,
        blocks_room=order.blocks_room,
        assignee=people.get(order.assignee_id) if order.assignee_id is not None else None,
        deadline_at=order.deadline_at,
        escalation_level=order.escalation_level,
        rating=order.rating,
        timeline=[
            s.TimelineItem(
                at=event.at,
                actor=people.get(event.actor_id) if event.actor_id is not None else None,
                action=event.action,
                from_status=event.from_status,
                to_status=event.to_status,
                note=event.note,
            )
            for event in events
        ],
    )


async def _brief(user_id: int) -> s.UserBrief:
    person = await clients.get_user(user_id)
    return s.UserBrief(id=person.id, username=person.username, name=person.name, dept_id=person.dept_id)
