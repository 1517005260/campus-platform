"""系统参数和运营统计。"""

from datetime import date, timedelta

import pytest
from app.config import settings
from app.models import Reservation, Room, RoomBlock, RoomOpenHour, Seat, Setting
from campus_common.testing import user_headers
from campus_common.timeutil import at_hour, now
from sqlalchemy import select

pytestmark = pytest.mark.db
DAY = date(2026, 10, 19)


def _room(
    db,
    *,
    name: str = "H3101",
    open_hour: int = 8,
    close_hour: int = 10,
    seats: int = 1,
) -> tuple[Room, list[Seat]]:
    room = Room(
        building="第三教学楼",
        floor=1,
        name=name,
        type="classroom",
        capacity=60,
        is_study_room=True,
        is_whole_bookable=True,
    )
    db.add(room)
    db.flush()
    db.add_all(
        [
            RoomOpenHour(room_id=room.id, weekday=weekday, open_hour=open_hour, close_hour=close_hour)
            for weekday in range(7)
        ]
    )
    rows = [Seat(room_id=room.id, code=f"A-{index:02d}") for index in range(1, seats + 1)]
    db.add_all(rows)
    db.commit()
    return room, rows


def _reservation(
    db,
    room: Room,
    seat: Seat,
    *,
    start_hour: int,
    end_hour: int,
    status: str,
    user_id: int = 1001,
):
    row = Reservation(
        user_id=user_id,
        seat_id=seat.id,
        room_id=room.id,
        start_at=at_hour(DAY, start_hour),
        end_at=at_hour(DAY, end_hour),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def test_settings_defaults_and_update(client, db, as_student, as_config):
    default = client.get("/api/v1/seat/settings", headers=as_student)
    assert default.status_code == 200
    assert default.json() == {
        "max_hours": 4,
        "remind_before_min": 15,
        "remind_late_min": 10,
        "auto_cancel_min": 15,
    }

    updated = client.put(
        "/api/v1/seat/settings",
        json={
            "max_hours": 3,
            "remind_before_min": 20,
            "remind_late_min": 8,
            "auto_cancel_min": 12,
        },
        headers=as_config,
    )
    assert updated.status_code == 200
    assert client.get("/api/v1/seat/settings", headers=as_student).json() == updated.json()
    db.expire_all()
    assert db.scalar(select(Setting.value).where(Setting.key == "max_hours")) == 3


@pytest.mark.parametrize(("remind_late_min", "status"), [(14, 200), (15, 422), (16, 422)])
def test_settings_late_reminder_must_precede_auto_cancel(client, db, as_config, remind_late_min, status):
    response = client.put(
        "/api/v1/seat/settings",
        json={
            "max_hours": 4,
            "remind_before_min": 15,
            "remind_late_min": remind_late_min,
            "auto_cancel_min": 15,
        },
        headers=as_config,
    )
    assert response.status_code == status
    if status == 422:
        assert response.json()["code"] == "VALIDATION_ERROR"
        db.expire_all()
        assert db.scalar(select(Setting.value).where(Setting.key == "remind_late_min")) is None


def test_settings_update_affects_new_reservation(client, db, as_config):
    room, (seat,) = _room(db, open_hour=8, close_hour=22)
    combined = user_headers(settings, perms=["seat:config", "seat:reserve"], dept_id=1)
    client.put(
        "/api/v1/seat/settings",
        json={
            "max_hours": 2,
            "remind_before_min": 15,
            "remind_late_min": 10,
            "auto_cancel_min": 15,
        },
        headers=as_config,
    ).raise_for_status()

    response = client.post(
        "/api/v1/seat/reservations",
        json={
            "seat_id": seat.id,
            "date": (now().date() + timedelta(days=2)).isoformat(),
            "start_hour": 10,
            "end_hour": 13,
        },
        headers=combined,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DURATION"


def test_settings_update_requires_config_permission(client, db, as_student):
    response = client.put(
        "/api/v1/seat/settings",
        json={
            "max_hours": 3,
            "remind_before_min": 20,
            "remind_late_min": 8,
            "auto_cancel_min": 12,
        },
        headers=as_student,
    )
    assert response.status_code == 403


def test_usage_stats_uses_checked_hours_and_no_show_denominator(client, db, as_stats):
    room, seats = _room(db, seats=2)
    _reservation(db, room, seats[0], start_hour=8, end_hour=10, status="completed", user_id=1001)
    _reservation(db, room, seats[1], start_hour=8, end_hour=9, status="no_show", user_id=1002)

    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": room.id},
        headers=as_stats,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["utilization"] == pytest.approx(0.5)
    assert body["no_show_rate"] == pytest.approx(0.5)
    assert body["by_room"] == [
        {"room_id": room.id, "utilization": 0.5, "no_show_rate": 0.5, "reservations": 2}
    ]
    assert body["by_hour"]["8"] == pytest.approx(0.5)
    assert body["by_hour"]["9"] == pytest.approx(0.5)
    assert body["by_hour"]["10"] == 0.0


def test_usage_stats_counts_only_checked_in_and_closed_reservations(client, db, as_stats):
    room, seats = _room(db, seats=5)
    for seat, status in zip(
        seats, ["completed", "no_show", "cancelled", "booked", "checked_in"], strict=True
    ):
        _reservation(db, room, seat, start_hour=8, end_hour=10, status=status, user_id=1000 + seat.id)

    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": room.id},
        headers=as_stats,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["no_show_rate"] == pytest.approx(0.5)  # no_show / (no_show + completed)
    assert body["utilization"] == pytest.approx(0.4)  # completed + checked_in：4 座位小时 / 10
    assert body["by_hour"]["8"] == pytest.approx(0.4)
    assert body["by_room"][0]["reservations"] == 5


def test_usage_stats_does_not_merge_simultaneous_seats(client, db, as_stats):
    room, seats = _room(db, seats=2)
    _reservation(db, room, seats[0], start_hour=8, end_hour=10, status="completed", user_id=1001)
    _reservation(db, room, seats[1], start_hour=8, end_hour=10, status="completed", user_id=1002)

    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": room.id},
        headers=as_stats,
    )

    assert response.status_code == 200
    assert response.json()["utilization"] == pytest.approx(1.0)
    assert response.json()["no_show_rate"] == 0.0


def test_usage_stats_excludes_room_block_from_open_hours(client, db, as_stats):
    room, (seat,) = _room(db, seats=1)
    db.add(
        RoomBlock(
            room_id=room.id,
            source="M3_MAINTENANCE",
            ref_id=7,
            start_at=at_hour(DAY, 8),
            end_at=at_hour(DAY, 9),
            reason="维修",
            created_by="m3-repair",
        )
    )
    db.commit()
    _reservation(db, room, seat, start_hour=9, end_hour=10, status="completed")

    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": room.id},
        headers=as_stats,
    )

    assert response.status_code == 200
    assert response.json()["utilization"] == pytest.approx(1.0)
    assert response.json()["by_hour"]["8"] == 0.0
    assert response.json()["by_hour"]["9"] == pytest.approx(1.0)


def test_usage_stats_zero_when_no_closed_reservations(client, db, as_stats):
    room, _ = _room(db)
    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": room.id},
        headers=as_stats,
    )
    assert response.status_code == 200
    assert response.json()["utilization"] == 0.0
    assert response.json()["no_show_rate"] == 0.0
    assert response.json()["by_room"][0]["reservations"] == 0


def test_usage_stats_rejects_invalid_range(client, db, as_stats):
    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": (DAY - timedelta(days=1)).isoformat()},
        headers=as_stats,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DATE_RANGE"


def test_usage_stats_rejects_unknown_room(client, db, as_stats):
    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "room_id": 999},
        headers=as_stats,
    )
    assert response.status_code == 404


def test_usage_stats_requires_stats_permission(client, db, as_student):
    response = client.get(
        "/api/v1/seat/stats/usage",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat()},
        headers=as_student,
    )
    assert response.status_code == 403
