"""M1 定时扫描任务的业务逻辑（同步会话，由 worker.py 调度）。

所有扫描遵循同一模式，写新任务时照抄 mark_no_shows：
  1. SELECT ... WHERE <仍处于待处理状态> FOR UPDATE SKIP LOCKED LIMIT n
     多个 worker 并发扫描不会拿到同一行；被签到等操作锁住的行本轮跳过。
  2. 在同一事务里改状态、写关联记录、写 outbox 消息。
  3. 状态条件写在 WHERE 里，处理过的行下一轮不会再被选中，所以任务可以安全重复执行。
"""

from datetime import datetime, timedelta

from campus_common.events import NotificationSend, Ref
from campus_common.outbox import add_event
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Outbox, Reservation, Violation
from app.rules import load_rules
from app.shared import PRODUCER, release_reservation

BATCH = 100


def mark_no_shows(session: Session, at: datetime) -> list[int]:
    """开始后 auto_cancel_min 分钟仍未签到：取消预约、释放座位、记违约、通知学生。

    调用方负责事务（session.begin()）。返回本轮处理的预约 ID。
    """
    rules = load_rules(session)
    deadline = at - timedelta(minutes=rules.auto_cancel_min)
    rows = session.scalars(
        select(Reservation)
        .where(Reservation.status == "booked", Reservation.start_at <= deadline)
        .order_by(Reservation.start_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()

    for r in rows:
        release_reservation(session, r, "NO_CHECK_IN", at=at, notify="seat.no_show_cancelled")
        session.add(Violation(user_id=r.user_id, reservation_id=r.id))
    return [r.id for r in rows]


def send_reminders_before(session: Session, at: datetime) -> list[int]:
    """发送开始前提醒；每条约会只发送一次。"""
    rules = load_rules(session)
    latest = at + timedelta(minutes=rules.remind_before_min)
    rows = session.scalars(
        select(Reservation)
        .where(
            Reservation.status == "booked",
            Reservation.reminded_before_at.is_(None),
            Reservation.start_at <= latest,
            Reservation.start_at > at,
        )
        .order_by(Reservation.start_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()

    for r in rows:
        r.reminded_before_at = at
        add_event(
            session,
            Outbox,
            PRODUCER,
            NotificationSend(
                user_ids=[r.user_id],
                template="seat.remind_before",
                params={
                    "reservation_id": r.id,
                    "start_at": r.start_at.isoformat(),
                    "end_at": r.end_at.isoformat(),
                },
                ref=Ref(module="m1", type="reservation", id=r.id),
            ),
        )
    return [r.id for r in rows]


def send_reminders_late(session: Session, at: datetime) -> list[int]:
    """发送未签到提醒；到达自动取消截止时间后不再发送。"""
    rules = load_rules(session)
    earliest = at - timedelta(minutes=rules.remind_late_min)
    deadline = at - timedelta(minutes=rules.auto_cancel_min)
    rows = session.scalars(
        select(Reservation)
        .where(
            Reservation.status == "booked",
            Reservation.reminded_late_at.is_(None),
            Reservation.start_at <= earliest,
            Reservation.start_at > deadline,
        )
        .order_by(Reservation.start_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()

    for r in rows:
        r.reminded_late_at = at
        add_event(
            session,
            Outbox,
            PRODUCER,
            NotificationSend(
                user_ids=[r.user_id],
                template="seat.remind_late",
                params={
                    "reservation_id": r.id,
                    "start_at": r.start_at.isoformat(),
                    "deadline_minutes": rules.auto_cancel_min,
                },
                ref=Ref(module="m1", type="reservation", id=r.id),
            ),
        )
    return [r.id for r in rows]


def complete_finished(session: Session, at: datetime) -> list[int]:
    """把已经结束且完成签到的预约标记为 completed。"""
    rows = session.scalars(
        select(Reservation)
        .where(
            Reservation.status == "checked_in",
            Reservation.end_at <= at,
        )
        .order_by(Reservation.end_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()

    for r in rows:
        r.status = "completed"
    return [r.id for r in rows]
