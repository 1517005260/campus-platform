"""M2 定时扫描任务。模式与 M1 jobs.py 相同：SKIP LOCKED 抢行 + 状态条件 + 同事务写 outbox。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, ApprovalRecord
from app.room_service import notify, status_event

BATCH = 100


def expire_overdue(session: Session, at: datetime) -> list[int]:
    """待实现（REQ-M2-05）：当前级别超过 deadline_at 仍未审批的 pending 申请 → expired，
    写审批记录，通知申请人。

    申请只有在最终通过后才会占用 M1，pending 状态下没有占用需要释放。
    与审批人"通过"并发时由 version 乐观锁保证只有一方成功。
    """
    applications = session.scalars(
        select(Application)
        .where(Application.status == "pending", Application.deadline_at <= at)
        .order_by(Application.id)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    expired = []
    for application in applications:
        application.status = "expired"
        session.add(
            ApprovalRecord(
                application_id=application.id,
                level=application.current_level,
                approver_id=None,
                action="expire",
                comment="当前审批级别已超时",
                at=at,
            )
        )
        notify(
            session,
            application,
            "room.application_expired",
            user_ids=[application.applicant_id],
            level=application.current_level,
        )
        status_event(session, application, "pending", "expired")
        expired.append(application.id)
    return expired
