"""M3 定时扫描任务。模式与 M1 jobs.py 相同：SKIP LOCKED 抢行 + 状态条件 + 同事务写 outbox。"""

import asyncio
from datetime import datetime, timedelta

from campus_common.events import NotificationSend, Ref
from campus_common.outbox import add_event
from campus_common.params import load_params
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clients
from app import schemas as s
from app.config import settings
from app.models import Outbox, Setting, WorkOrder, WorkOrderEvent

BATCH = 100
PRODUCER = settings.service_name


def escalate_overdue(session: Session, at: datetime) -> list[int]:
    """工单在某状态停留超过 timeout_hours 时 escalation_level + 1，写时间线并通知。状态不变。

    计时起点是进入当前状态的时间与上次升级时间中较晚的一个，同一段超时只升级一次。
    """
    rules = load_params(session, Setting, s.RepairSettings)
    recipients = asyncio.run(_recipients(rules))
    rows = session.scalars(
        select(WorkOrder)
        .where(WorkOrder.status.in_({rule.status for rule in rules.escalation_rules}))
        .order_by(WorkOrder.id)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    done: list[int] = []
    for order in rows:
        if _escalate(session, order, rules, recipients, at):
            done.append(order.id)
    return done


def _escalate(
    session: Session, order: WorkOrder, rules: s.RepairSettings, recipients: dict, at: datetime
) -> bool:
    changed = False
    for rule in rules.escalation_rules:
        if rule.status != order.status:
            continue
        if _anchor(session, order) + timedelta(hours=rule.timeout_hours) > at:
            continue
        order.escalation_level += 1
        session.add(
            WorkOrderEvent(
                order_id=order.id,
                at=at,
                actor_id=None,
                action="escalate",
                from_status=order.status,
                to_status=order.status,
                note=f"升级到 {order.escalation_level}",
            )
        )
        session.flush()
        user_ids = recipients.get(rule.notify_perm, [])
        if user_ids:
            add_event(
                session,
                Outbox,
                PRODUCER,
                NotificationSend(
                    user_ids=user_ids,
                    template="repair.escalated",
                    params={"order_id": order.id, "status": order.status, "level": order.escalation_level},
                    ref=Ref(module="m3", type="work_order", id=order.id),
                ),
            )
        changed = True
    return changed


def _anchor(session: Session, order: WorkOrder) -> datetime:
    entered = session.scalar(
        select(WorkOrderEvent.at)
        .where(
            WorkOrderEvent.order_id == order.id,
            WorkOrderEvent.to_status == order.status,
            WorkOrderEvent.action != "escalate",
        )
        .order_by(WorkOrderEvent.id.desc())
        .limit(1)
    )
    escalated = session.scalar(
        select(WorkOrderEvent.at)
        .where(WorkOrderEvent.order_id == order.id, WorkOrderEvent.action == "escalate")
        .order_by(WorkOrderEvent.id.desc())
        .limit(1)
    )
    base = entered or order.created_at
    if escalated is not None and escalated > base:
        return escalated
    return base


async def _recipients(rules: s.RepairSettings) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for perm in {rule.notify_perm for rule in rules.escalation_rules}:
        found[perm] = [person.id for person in await clients.users_with_perm(perm)]
    return found
