"""定时任务：未签到自动取消。时间由参数注入，不依赖真实时钟。"""

from datetime import date, timedelta

import pytest
from app.jobs import complete_finished, mark_no_shows, send_reminders_before, send_reminders_late
from app.models import Outbox, Reservation, Room, Seat, SeatStatusLog, Setting, Violation
from campus_common.timeutil import at_hour
from sqlalchemy import func, select

pytestmark = pytest.mark.db
DAY = date(2026, 10, 20)
START = at_hour(DAY, 14)


@pytest.fixture
def booked(db):
    room = Room(building="三教", floor=1, name="H3106", type="classroom", capacity=60)
    db.add(room)
    db.flush()
    seat = Seat(room_id=room.id, code="A-01")
    db.add(seat)
    db.flush()
    r = Reservation(
        user_id=42,
        seat_id=seat.id,
        room_id=room.id,
        start_at=START,
        end_at=START + timedelta(hours=2),
        status="booked",
    )
    db.add(r)
    db.commit()
    return r


def _count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_not_cancelled_before_deadline(db, booked):
    with db.begin():
        assert mark_no_shows(db, START + timedelta(minutes=14)) == []
    assert db.get(Reservation, booked.id).status == "booked"


def test_cancelled_after_deadline_with_violation_and_notification(db, booked):
    with db.begin():
        assert mark_no_shows(db, START + timedelta(minutes=15)) == [booked.id]

    db.expire_all()
    r = db.get(Reservation, booked.id)
    assert (r.status, r.cancel_reason) == ("no_show", "NO_CHECK_IN")
    assert _count(db, Violation, Violation.user_id == 42) == 1
    assert _count(db, SeatStatusLog, SeatStatusLog.source == "M1_RESERVATION") == 1
    types = set(db.scalars(select(Outbox.type)))
    assert types == {"notification.send", "m1.reservation.cancelled"}


def test_running_twice_does_not_double_count(db, booked):
    for _ in range(2):
        with db.begin():
            mark_no_shows(db, START + timedelta(minutes=30))
    assert _count(db, Violation) == 1
    assert _count(db, Outbox) == 2


def test_checked_in_reservation_untouched(db, booked):
    booked.status = "checked_in"
    db.commit()
    with db.begin():
        assert mark_no_shows(db, START + timedelta(minutes=30)) == []


def test_respects_configured_deadline(db, booked):
    db.add(Setting(key="auto_cancel_min", value=30))
    db.commit()
    with db.begin():
        assert mark_no_shows(db, START + timedelta(minutes=20)) == []


def test_before_reminder_not_sent_before_window(db, booked):
    with db.begin():
        assert send_reminders_before(db, START - timedelta(minutes=16)) == []
    db.expire_all()
    assert db.get(Reservation, booked.id).reminded_before_at is None
    assert _count(db, Outbox) == 0


def test_before_reminder_sent_at_window_start_once(db, booked):
    with db.begin():
        assert send_reminders_before(db, START - timedelta(minutes=15)) == [booked.id]
    with db.begin():
        assert send_reminders_before(db, START - timedelta(minutes=14)) == []

    db.expire_all()
    row = db.get(Reservation, booked.id)
    assert row.reminded_before_at == START - timedelta(minutes=15)
    assert _count(db, Outbox, Outbox.type == "notification.send") == 1
    envelope = db.scalar(select(Outbox)).envelope
    assert envelope["payload"]["template"] == "seat.remind_before"
    assert envelope["payload"]["ref"]["id"] == booked.id


def test_before_reminder_skipped_after_start(db, booked):
    with db.begin():
        assert send_reminders_before(db, START) == []
    db.expire_all()
    assert db.get(Reservation, booked.id).reminded_before_at is None


def test_before_reminder_respects_configured_window(db, booked):
    db.add(Setting(key="remind_before_min", value=30))
    db.commit()
    with db.begin():
        assert send_reminders_before(db, START - timedelta(minutes=20)) == [booked.id]


def test_late_reminder_not_sent_before_window(db, booked):
    with db.begin():
        assert send_reminders_late(db, START + timedelta(minutes=9)) == []
    db.expire_all()
    assert db.get(Reservation, booked.id).reminded_late_at is None
    assert _count(db, Outbox) == 0


def test_late_reminder_sent_at_window_start_once(db, booked):
    with db.begin():
        assert send_reminders_late(db, START + timedelta(minutes=10)) == [booked.id]
    with db.begin():
        assert send_reminders_late(db, START + timedelta(minutes=11)) == []

    db.expire_all()
    row = db.get(Reservation, booked.id)
    assert row.reminded_late_at == START + timedelta(minutes=10)
    assert _count(db, Outbox, Outbox.type == "notification.send") == 1
    envelope = db.scalar(select(Outbox)).envelope
    assert envelope["payload"]["template"] == "seat.remind_late"


def test_late_reminder_not_sent_at_auto_cancel_deadline(db, booked):
    with db.begin():
        assert send_reminders_late(db, START + timedelta(minutes=15)) == []
    db.expire_all()
    assert db.get(Reservation, booked.id).reminded_late_at is None


def test_late_reminder_ignores_checked_in_reservation(db, booked):
    booked.status = "checked_in"
    db.commit()
    with db.begin():
        assert send_reminders_late(db, START + timedelta(minutes=10)) == []
    db.expire_all()
    assert db.get(Reservation, booked.id).reminded_late_at is None


def test_complete_finished_at_end_boundary_once(db, booked):
    booked.status = "checked_in"
    db.commit()
    with db.begin():
        assert complete_finished(db, booked.end_at - timedelta(seconds=1)) == []
    with db.begin():
        assert complete_finished(db, booked.end_at) == [booked.id]
    with db.begin():
        assert complete_finished(db, booked.end_at + timedelta(minutes=1)) == []

    db.expire_all()
    assert db.get(Reservation, booked.id).status == "completed"


def test_complete_finished_ignores_unfinished_or_not_checked_in(db, booked):
    with db.begin():
        assert complete_finished(db, booked.end_at + timedelta(hours=1)) == []

    booked.status = "checked_in"
    db.commit()
    with db.begin():
        assert complete_finished(db, booked.end_at - timedelta(minutes=1)) == []
