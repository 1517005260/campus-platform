"""M2 定时扫描任务。模式与 M1 jobs.py 相同：条件写在 WHERE 里 + SKIP LOCKED 抢行 + 同事务写 outbox。"""

import asyncio
import logging
from datetime import datetime, timedelta

from campus_common.errors import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clients
from app.models import Application
from app.room_service import notify, overdue, transition

log = logging.getLogger(__name__)

BATCH = 100
RELEASE_BATCH = 20  # 每条都要调用 M1，批次小一些，避免长时间持有行锁
# 大于 M1 客户端超时（5 秒）：在途的占用请求结束之后才释放，释放后不会再出现该申请的新占用
RELEASE_GRACE = timedelta(minutes=1)


def expire_overdue(session: Session, at: datetime) -> list[int]:
    """当前级别到了截止时间（deadline_at <= at）或申请时段已开始（start_at <= at）仍未审批完成的
    pending 申请 → expired，写审批记录（系统动作），通知申请人。调用方负责事务，返回本轮撤销的申请 ID。

    与审批人操作并发时：审批人先提交则本任务的 version 校验失败、整轮回滚后下一轮重来；
    本任务先锁住行则审批人提交时 version 冲突，得到 409。"""
    applications = session.scalars(
        select(Application)
        .where(Application.status == "pending", overdue(at))
        .order_by(Application.id)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    for application in applications:
        timed_out = application.deadline_at <= at
        transition(
            session,
            application,
            "expire",
            "expired",
            at,
            comment="当前级别审批超时" if timed_out else "申请时段已开始，审批未完成",
        )
        notify(
            session,
            application,
            "room.application_expired",
            user_ids=[application.applicant_id],
            level=application.current_level,
            cause="deadline" if timed_out else "started",
        )
    return [application.id for application in applications]


def release_leftover_blocks(session: Session, at: datetime) -> list[int]:
    """释放未通过就结束（驳回、撤回、超时撤销）的申请在 M1 可能残留的占用。

    最终审批请求 M1 占用后失败（例如 M1 超时但其实已占用），申请之后未通过就结束时，教室会一直被占用。
    请求占用前申请上已记下 occupy_requested_at，这里在其 RELEASE_GRACE 之后释放（M1 幂等，没有占用时
    返回 False）并清空；M1 不可用时保留，下一轮重试。返回本轮处理完的申请 ID。"""
    applications = session.scalars(
        select(Application)
        .where(
            Application.status.in_(("rejected", "withdrawn", "expired")),
            Application.occupy_requested_at <= at - RELEASE_GRACE,
        )
        .order_by(Application.id)
        .limit(RELEASE_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    released = []
    for application in applications:
        try:
            asyncio.run(clients.release_room(application.id))
        except AppError as exc:
            log.warning("释放申请 %s 的残留占用失败，下一轮重试：%s", application.id, exc.code)
            continue
        application.occupy_requested_at = None
        released.append(application.id)
    return released
