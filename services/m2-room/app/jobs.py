"""M2 定时扫描任务。模式与 M1 jobs.py 相同：条件写在 WHERE 里 + SKIP LOCKED 抢行 + 同事务写 outbox。"""

import asyncio
import logging
from datetime import datetime

from campus_common.errors import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clients
from app.models import Application
from app.room_service import notify, occupy_in_flight, overdue, transition

log = logging.getLogger(__name__)

BATCH = 100
RELEASE_BATCH = 20  # 每条都要调用 M1，批次小一些，避免长时间持有行锁


def expire_overdue(session: Session, at: datetime) -> list[int]:
    """当前级别到了截止时间（deadline_at <= at）或申请时段已开始（start_at <= at）仍未审批完成的
    pending 申请 → expired，写审批记录（系统动作），通知申请人。调用方负责事务，返回本轮撤销的申请 ID。
    最终审批的占用请求可能在途（occupy_in_flight）的申请本轮跳过，RELEASE_GRACE 之后再撤销。

    与审批人操作并发时：审批人先提交则本任务的 version 校验失败、整轮回滚后下一轮重来；
    本任务先锁住行则审批人提交时 version 冲突，得到 409。"""
    applications = session.scalars(
        select(Application)
        .where(Application.status == "pending", overdue(at), ~occupy_in_flight(at))
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
    请求占用前申请上已记下 occupy_requested_at，这里等请求不再可能在途（occupy_in_flight 为假）后释放
    （M1 幂等，没有占用时返回 False）并清空。等待时长远大于 M1 客户端超时，但不能绝对保证 M1 端已处理完：
    M1 处理超过 RELEASE_GRACE 才提交占用时，释放会落在占用之前（返回 False），之后建立的占用本任务不会再释放。

    M1 释放失败时把 occupy_requested_at 推到本轮时刻：RELEASE_GRACE 之后重试，并按该时间排到队尾，
    持续失败的申请不会挡住其他申请。返回本轮释放完的申请 ID。"""
    applications = session.scalars(
        select(Application)
        .where(
            Application.status.in_(("rejected", "withdrawn", "expired")),
            Application.occupy_requested_at.is_not(None),
            ~occupy_in_flight(at),
        )
        .order_by(Application.occupy_requested_at, Application.id)
        .limit(RELEASE_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    released = []
    for application in applications:
        try:
            asyncio.run(clients.release_room(application.id))
        except AppError as exc:
            log.warning("释放申请 %s 的残留占用失败，稍后重试：%s", application.id, exc.code)
            application.occupy_requested_at = at
            continue
        application.occupy_requested_at = None
        released.append(application.id)
    return released
