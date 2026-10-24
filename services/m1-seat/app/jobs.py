"""M1 定时扫描任务的业务逻辑（同步会话，由 worker.py 调度）。

所有扫描遵循同一模式，写新任务时照抄 mark_no_shows：
  1. SELECT ... WHERE <仍处于待处理状态> FOR UPDATE SKIP LOCKED LIMIT n
     多个 worker 并发扫描不会拿到同一行；被签到等操作锁住的行本轮跳过。
  2. 在同一事务里改状态、写关联记录、写 outbox 消息。
  3. 状态条件写在 WHERE 里，处理过的行下一轮不会再被选中，所以任务可以安全重复执行。
"""

from datetime import datetime, timedelta

from campus_common.events import NotificationSend, Ref, ReservationCancelled
from campus_common.outbox import add_event
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Outbox, Reservation, SeatStatusLog, Violation
from app.rules import load_rules

PRODUCER = settings.service_name
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
        r.status = "no_show"
        r.cancel_reason = "NO_CHECK_IN"
        session.add(Violation(user_id=r.user_id, reservation_id=r.id))
        session.add(
            SeatStatusLog(
                seat_id=r.seat_id,
                at=at,
                state="released",
                source="M1_RESERVATION",
                ref_id=r.id,
                start_at=r.start_at,
                end_at=r.end_at,
            )
        )
        add_event(
            session,
            Outbox,
            PRODUCER,
            NotificationSend(
                user_ids=[r.user_id],
                template="seat.no_show_cancelled",
                params={"reservation_id": r.id, "start_at": r.start_at.isoformat()},
                ref=Ref(module="m1", type="reservation", id=r.id),
            ),
        )
        add_event(
            session,
            Outbox,
            PRODUCER,
            ReservationCancelled(reservation_id=r.id, user_id=r.user_id, reason="NO_SHOW"),
        )
    return [r.id for r in rows]


def send_reminders_before(session: Session, at: datetime) -> list[int]:
    """待实现（REQ-M1-07）：开始前 remind_before_min 分钟提醒。用 reminded_before_at 标记，保证只提醒一次。"""
    return []


def send_reminders_late(session: Session, at: datetime) -> list[int]:
    """待实现（REQ-M1-08）：开始后 remind_late_min 分钟仍未签到再提醒一次。用 reminded_late_at 标记。"""
    return []


def complete_finished(session: Session, at: datetime) -> list[int]:
    """待实现：已签到且 end_at 已过的预约标记为 completed。"""
    return []
