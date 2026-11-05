"""M3 定时扫描任务。模式与 M1 jobs.py 相同：到期条件写在 WHERE 里 + SKIP LOCKED 抢行 + 同事务写 outbox。"""

from datetime import datetime, timedelta

from campus_common.params import load_params
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.models import Setting, WorkOrder, WorkOrderEvent
from app.orders import notify

BATCH = 100


def escalate_overdue(session: Session, at: datetime) -> list[int]:
    """工单在某状态停留超过规则的 timeout_hours 时 escalation_level + 1，写时间线并通知 notify_perm。

    状态不变。

    计时起点是进入当前状态的时间与上次升级时间中较晚的一个（起点 + timeout_hours 正好等于 at 时升级），
    因此同一段超时只升级一次，再过一个周期升级下一次。通知按权限码寻址，由 common 解析收件人，
    common 不可用时升级照常进行、通知在消息队列中等待。调用方负责事务，返回本轮升级的工单 ID。
    """
    rules = load_params(session, Setting, s.RepairSettings)
    anchor = func.greatest(WorkOrder.status_changed_at, WorkOrder.last_escalated_at)
    done: list[int] = []
    for rule in rules.escalation_rules:
        rows = session.scalars(
            select(WorkOrder)
            .where(WorkOrder.status == rule.status, anchor <= at - timedelta(hours=rule.timeout_hours))
            .order_by(WorkOrder.id)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        ).all()
        for order in rows:
            order.escalation_level += 1
            order.last_escalated_at = at
            session.add(
                WorkOrderEvent(
                    order_id=order.id,
                    at=at,
                    actor_id=None,
                    action="escalate",
                    from_status=order.status,
                    to_status=order.status,
                    note=f"超过 {rule.timeout_hours} 小时，升级到第 {order.escalation_level} 级",
                )
            )
            notify(
                session,
                order,
                "repair.escalated",
                perm=rule.notify_perm,
                status=order.status,
                since=order.status_changed_at.isoformat(),
                timeout_hours=rule.timeout_hours,
                level=order.escalation_level,
            )
            done.append(order.id)
    return done
