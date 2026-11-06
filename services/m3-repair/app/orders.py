"""工单状态机与查询。

- 状态迁移只走 _move()：检查当前状态、写 WorkOrderEvent、刷新 status_changed_at（超时升级的计时起点）、
  发 m3.workorder.status_changed。
- 需要 M1 配合的迁移先调用 M1，成功后才提交本地状态：开始维修见 start()，验收见 accept()。
- 看不到工单的人（不是报修人、被指派的维修工，也没有调度/管理权限）做任何操作都得到 404，不暴露工单是否存在；
  看得到但无权执行该操作时 403。
- 显示用的人员信息来自 user_snapshots（参与工单时写入），读接口不调用 common。
- 通知经 outbox 发出；发给调度员、管理员这类"拥有某权限的人"时按权限码寻址，由 common 解析收件人。
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.clients.common import UserBrief
from campus_common.errors import AppError, not_found
from campus_common.events import NotificationSend, Ref, WorkOrderStatusChanged
from campus_common.outbox import add_event
from campus_common.pagination import Page, PageParams, page_of, paginate
from campus_common.params import aload_params, asave_params
from campus_common.timeutil import now
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients
from app import schemas as s
from app.config import settings
from app.models import Outbox, Setting, UserSnapshot, WorkOrder, WorkOrderEvent

PRODUCER = settings.service_name


# ---------- 报修人 ----------


async def report(session: AsyncSession, user: CurrentUser, body: s.OrderCreate) -> s.WorkOrder:
    room = await _ensure_room(body.room_id)
    if body.seat_id is not None and body.seat_id not in {seat.id for seat in room.seats}:
        raise AppError(400, "SEAT_NOT_IN_ROOM", "座位不属于该教室")
    at = now()
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
            blocks_room=False,
            escalation_level=0,
        )
        session.add(order)
        await _move(session, order, user.id, "report", "submitted", at, expected=None)
        await _remember(session, user)
        notify(session, order, "repair.reported", perm="repair:dispatch", room=f"{room.building} {room.name}")
        return await _present(session, order)


async def cancel(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.CancelRequest
) -> s.WorkOrder:
    at = now()
    async with session.begin():
        order = await _load(session, user, order_id, lock=True)
        if order.reporter_id != user.id:
            raise AppError(403, "FORBIDDEN", "只有报修人可以取消")
        await _remember(session, user)
        await _move(
            session, order, user.id, "cancel", "cancelled", at, expected="submitted", note=body.reason
        )
        # 派单前取消：还没有维修工，告知收到上报通知的调度员不必再派单
        notify(session, order, "repair.cancelled", perm="repair:dispatch", reason=body.reason)
        return await _present(session, order)


async def accept(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.AcceptRequest
) -> s.WorkOrder:
    at = now()
    async with session.begin():
        order = await _load(session, user, order_id, lock=True)
        _require_status(order, "pending_acceptance")
        rules = await aload_params(session, Setting, s.RepairSettings)
        by_admin = _check_acceptor(user, order, rules, at)
        if order.blocks_room:
            # 持有工单行锁调用 M1：并发的"验收不通过"要等本事务结束，看到 closed 后返回 409。
            # M1 中已释放的占用不能再用同一单号下架，因此不能先释放、再在另一个事务里发现状态已变。
            # 本地提交失败时教室已恢复、工单仍待验收，重试验收会再次释放（幂等）后关闭。
            await clients.release_room(order.id)
        await _remember(session, user)
        action = "admin_accept" if by_admin else "accept"
        await _move(
            session, order, user.id, action, "closed", at, expected="pending_acceptance", note=body.comment
        )
        order.rating, order.rating_comment, order.closed_by = body.rating, body.comment, user.id
        notify(
            session,
            order,
            "repair.accepted",
            user_ids=[order.assignee_id],
            rating=body.rating,
            by_admin=by_admin,
        )
        return await _present(session, order)


async def reject(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.RejectAcceptanceRequest
) -> s.WorkOrder:
    at = now()
    async with session.begin():
        order = await _load(session, user, order_id, lock=True)
        if order.reporter_id != user.id:
            raise AppError(403, "FORBIDDEN", "只有报修人可以拒绝验收")
        await _remember(session, user)
        await _move(
            session,
            order,
            user.id,
            "reject",
            "in_progress",
            at,
            expected="pending_acceptance",
            note=body.reason,
        )
        notify(
            session,
            order,
            "repair.rejected",
            user_ids=[order.assignee_id],
            reason=body.reason,
            blocks_room=order.blocks_room,
        )
        return await _present(session, order)


# ---------- 调度员与维修工 ----------


async def dispatch(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.DispatchRequest
) -> s.WorkOrder:
    at = now()
    if body.deadline_at <= at:
        raise AppError(400, "DEADLINE_NOT_FUTURE", "截止时间必须晚于现在")
    workers = await clients.users_with_perm("repair:work")
    assignee = next((person for person in workers if person.id == body.assignee_id), None)
    if assignee is None:
        raise AppError(400, "ASSIGNEE_NOT_WORKER", "派单对象没有维修权限")
    async with session.begin():
        order = await _load(session, user, order_id, lock=True)
        await _remember(session, user, assignee)
        await _move(session, order, user.id, "dispatch", "dispatched", at, expected="submitted")
        order.assignee_id, order.deadline_at, order.blocks_room = (
            assignee.id,
            body.deadline_at,
            body.blocks_room,
        )
        notify(
            session,
            order,
            "repair.dispatched",
            user_ids=[assignee.id],
            deadline_at=body.deadline_at.isoformat(),
            blocks_room=body.blocks_room,
        )
        return await _present(session, order)


async def start(session: AsyncSession, user: CurrentUser, order_id: int) -> s.WorkOrder:
    at = now()
    async with session.begin():
        order = await _assigned(session, user, order_id)
        _require_status(order, "dispatched")
        if order.blocks_room and order.block_start_at is None:
            # 先提交下架起点再调用 M1：M1 按幂等键核对请求内容，重试必须发出完全相同的请求
            order.block_start_at = at
    if order.blocks_room:
        await clients.block_room(
            order.id, order.room_id, order.block_start_at, f"报修工单 #{order.id} 维修中"
        )
    async with session.begin():
        order = await _assigned(session, user, order_id)
        await _remember(session, user)
        await _move(session, order, user.id, "start", "in_progress", at, expected="dispatched")
        notify(session, order, "repair.started", user_ids=[order.reporter_id], blocks_room=order.blocks_room)
        return await _present(session, order)


async def complete(
    session: AsyncSession, user: CurrentUser, order_id: int, body: s.CompleteRequest
) -> s.WorkOrder:
    at = now()
    async with session.begin():
        order = await _assigned(session, user, order_id)
        await _remember(session, user)
        await _move(
            session,
            order,
            user.id,
            "complete",
            "pending_acceptance",
            at,
            expected="in_progress",
            note=body.note,
        )
        order.completed_at = at
        order.photos = [*order.photos, *body.photos]
        rules = await aload_params(session, Setting, s.RepairSettings)
        notify(
            session,
            order,
            "repair.completed",
            user_ids=[order.reporter_id],
            note=body.note,
            accept_after_hours=rules.admin_accept_after_hours,
        )
        return await _present(session, order)


# ---------- 查询与配置 ----------


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
    if not (user.has("repair:dispatch") or user.has("repair:manage")):
        stmt = stmt.where(WorkOrder.assignee_id == user.id)  # 只有 repair:work：只看派给自己的
    if status is not None:
        stmt = stmt.where(WorkOrder.status == status)
    if room_id is not None:
        stmt = stmt.where(WorkOrder.room_id == room_id)
    if assignee_id is not None:
        stmt = stmt.where(WorkOrder.assignee_id == assignee_id)
    if escalated is not None:
        stmt = stmt.where(WorkOrder.escalation_level > 0 if escalated else WorkOrder.escalation_level == 0)
    return await _page(session, stmt, params)


async def detail(session: AsyncSession, user: CurrentUser, order_id: int) -> s.WorkOrder:
    return await _present(session, await _load(session, user, order_id))


async def get_settings(session: AsyncSession) -> s.RepairSettings:
    return await aload_params(session, Setting, s.RepairSettings)


async def put_settings(session: AsyncSession, body: s.RepairSettings) -> s.RepairSettings:
    async with session.begin():
        await asave_params(session, Setting, body)
    return body


# ---------- 通知（定时任务共用） ----------


def notify(
    session,
    order: WorkOrder,
    template: str,
    *,
    user_ids: Iterable[int | None] = (),
    perm: str | None = None,
    **params,
) -> None:
    """把一条工单通知加入当前事务（同步或异步会话）。

    参数总带 order_id 与 category，模板登记在 common 的 app/templates.py。"""
    add_event(
        session,
        Outbox,
        PRODUCER,
        NotificationSend(
            user_ids=[user_id for user_id in user_ids if user_id is not None],
            perm=perm,
            template=template,
            params={"order_id": order.id, "category": order.category, **params},
            ref=Ref(module="m3", type="work_order", id=order.id),
        ),
    )


# ---------- 内部 ----------


async def _ensure_room(room_id: int):
    try:
        return await clients.get_room(room_id)
    except AppError as exc:
        if exc.status == 404 and exc.code == "NOT_FOUND":
            raise AppError(400, "ROOM_NOT_FOUND", "教室不存在") from exc
        raise


def _can_view(order: WorkOrder, user: CurrentUser) -> bool:
    if user.has("repair:dispatch") or user.has("repair:manage"):
        return True
    if user.has("repair:report") and order.reporter_id == user.id:
        return True
    return user.has("repair:work") and order.assignee_id == user.id


async def _load(session: AsyncSession, user: CurrentUser, order_id: int, *, lock: bool = False) -> WorkOrder:
    stmt = select(WorkOrder).where(WorkOrder.id == order_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    order = await session.scalar(stmt)
    if order is None or not _can_view(order, user):
        raise not_found("工单", order_id)
    return order


async def _assigned(session: AsyncSession, user: CurrentUser, order_id: int) -> WorkOrder:
    order = await _load(session, user, order_id, lock=True)
    if order.assignee_id != user.id:
        raise AppError(403, "NOT_ASSIGNEE", "只有被指派的维修工可以操作")
    return order


def _check_acceptor(user: CurrentUser, order: WorkOrder, rules: s.RepairSettings, at: datetime) -> bool:
    """报修人本人可以验收；repair:manage 在完工 admin_accept_after_hours 后（含该时刻）可代验收。

    返回是否为代验收。"""
    if order.reporter_id == user.id and user.has("repair:report"):
        return False
    if user.has("repair:manage"):
        if at < order.completed_at + timedelta(hours=rules.admin_accept_after_hours):
            raise AppError(403, "ADMIN_ACCEPT_TOO_EARLY", "未到管理员代验收时间")
        return True
    raise AppError(403, "FORBIDDEN", "只有报修人或到时代验收的管理员可以验收")


STATUS_LABELS: dict[s.OrderStatus, str] = {
    "submitted": "待派单",
    "dispatched": "已派单",
    "in_progress": "维修中",
    "pending_acceptance": "待验收",
    "closed": "已关闭",
    "cancelled": "已取消",
}


def _require_status(order: WorkOrder, expected: str | None) -> None:
    if order.status != expected:
        label = STATUS_LABELS[order.status]
        raise AppError(409, "ORDER_STATE_CONFLICT", f"工单当前为“{label}”，不能执行此操作")


async def _move(
    session: AsyncSession,
    order: WorkOrder,
    actor_id: int,
    action: s.TimelineAction,
    to_status: str,
    at: datetime,
    *,
    expected: str | None,
    note: str | None = None,
) -> None:
    """唯一的状态迁移：expected 为 None 表示新建工单。"""
    _require_status(order, expected)
    order.status, order.status_changed_at = to_status, at
    await session.flush()  # 新工单在这里取得 ID
    session.add(
        WorkOrderEvent(
            order_id=order.id,
            at=at,
            actor_id=actor_id,
            action=action,
            from_status=expected,
            to_status=to_status,
            note=note,
        )
    )
    add_event(
        session,
        Outbox,
        PRODUCER,
        WorkOrderStatusChanged(order_id=order.id, from_status=expected or "", to_status=to_status),
    )


async def _remember(session: AsyncSession, *people: CurrentUser | UserBrief) -> None:
    """写入或刷新参与工单的人的显示信息。"""
    unique = {person.id: person for person in people}
    stmt = insert(UserSnapshot).values(
        [{"id": p.id, "username": p.username, "name": p.name, "dept_id": p.dept_id} for p in unique.values()]
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[UserSnapshot.id],
            set_={column: stmt.excluded[column] for column in ("username", "name", "dept_id")},
        )
    )


async def _page(session: AsyncSession, stmt: Select, params: PageParams) -> Page[s.WorkOrder]:
    page = await paginate(session, stmt.order_by(WorkOrder.id.desc()), params, lambda order: order)
    return page_of(await _present_many(session, page.items), page.total, params)


async def _present(session: AsyncSession, order: WorkOrder) -> s.WorkOrder:
    (presented,) = await _present_many(session, [order])
    return presented


async def _present_many(session: AsyncSession, orders: list[WorkOrder]) -> list[s.WorkOrder]:
    """一页工单的时间线与人员各一次查询。"""
    if not orders:
        return []
    events = (
        await session.scalars(
            select(WorkOrderEvent)
            .where(WorkOrderEvent.order_id.in_([order.id for order in orders]))
            .order_by(WorkOrderEvent.id)
        )
    ).all()
    ids = {order.reporter_id for order in orders}
    ids |= {order.assignee_id for order in orders} | {event.actor_id for event in events}
    ids.discard(None)
    snapshots = {
        row.id: s.UserBrief.model_validate(row, from_attributes=True)
        for row in await session.scalars(select(UserSnapshot).where(UserSnapshot.id.in_(ids)))
    }

    def person(user_id: int | None) -> s.UserBrief | None:
        if user_id is None:
            return None
        # 本表上线前就已存在的工单可能没有快照：只显示 ID
        return snapshots.get(user_id) or s.UserBrief(
            id=user_id, username="", name=f"用户 {user_id}", dept_id=None
        )

    return [
        s.WorkOrder(
            id=order.id,
            reporter=person(order.reporter_id),
            room_id=order.room_id,
            seat_id=order.seat_id,
            category=order.category,
            description=order.description,
            photos=list(order.photos),
            status=order.status,
            blocks_room=order.blocks_room,
            assignee=person(order.assignee_id),
            deadline_at=order.deadline_at,
            escalation_level=order.escalation_level,
            rating=order.rating,
            timeline=[
                s.TimelineItem(
                    at=event.at,
                    actor=person(event.actor_id),
                    action=event.action,
                    from_status=event.from_status,
                    to_status=event.to_status,
                    note=event.note,
                )
                for event in events
                if event.order_id == order.id
            ],
        )
        for order in orders
    ]
