"""每日签到码和预约签到。时钟由 conftest 的 clock fixture 冻结，不依赖真实时间。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from app.config import settings
from app.main import app
from app.models import CheckinCode, Reservation, Room, Seat
from campus_common.testing import user_headers
from campus_common.timeutil import at_hour
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import DAY

pytestmark = pytest.mark.db
START = at_hour(DAY, 9)


def _room_with_seat(db) -> tuple[Room, Seat]:
    room = Room(
        building="第三教学楼",
        floor=1,
        name="H3101",
        type="classroom",
        capacity=60,
        is_study_room=True,
        is_whole_bookable=True,
    )
    db.add(room)
    db.flush()
    seat = Seat(room_id=room.id, code="A-01")
    db.add(seat)
    db.commit()
    return room, seat


def _reserve(
    db,
    room: Room,
    seat: Seat,
    *,
    start_at: datetime = START,
    status: str = "booked",
    user_id: int = 1001,
) -> Reservation:
    row = Reservation(
        user_id=user_id,
        seat_id=seat.id,
        room_id=room.id,
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def _code(db, room: Room, value: str = "123456") -> None:
    db.add(CheckinCode(room_id=room.id, valid_date=DAY, code=value))
    db.commit()


def _check_in(client, headers, reservation: Reservation, code: str = "123456"):
    return client.post(
        f"/api/v1/seat/reservations/{reservation.id}/check-in", json={"code": code}, headers=headers
    )


def test_checkin_code_is_stable_and_has_qr_payload(client, db, as_screen):
    room, _ = _room_with_seat(db)
    first = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)
    second = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["valid_date"] == DAY.isoformat()
    assert len(first.json()["code"]) == 6
    assert first.json()["code"].isdigit()
    assert first.json()["qr_payload"] == f"campus://checkin/{room.id}/{first.json()['code']}"
    assert db.scalar(select(func.count()).select_from(CheckinCode)) == 1


def test_checkin_code_generation_is_concurrency_safe(db, as_screen):
    room, _ = _room_with_seat(db)

    def fetch():
        with TestClient(app) as concurrent_client:
            return concurrent_client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: fetch(), range(4)))

    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["code"] for response in responses}) == 1
    assert db.scalar(select(func.count()).select_from(CheckinCode)) == 1


def test_checkin_code_requires_screen_permission(client, db, as_student):
    room, _ = _room_with_seat(db)
    response = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_student)
    assert response.status_code == 403


def test_checkin_code_rejects_unknown_room(client, db, as_screen):
    response = client.get("/api/v1/seat/rooms/999/checkin-code", headers=as_screen)
    assert response.status_code == 404


def test_early_morning_reservation_checks_in_with_code_on_screen(client, db, clock, as_screen, as_student):
    """北京时间 07:00 开始的预约（UTC 仍是前一天）用屏幕当天显示的码签到。"""
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=at_hour(DAY, 7))
    clock.move_to(at_hour(DAY, 7) - timedelta(minutes=10))
    screen = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen).json()

    response = _check_in(client, as_student, reservation, screen["code"])

    assert response.status_code == 200
    assert response.json()["status"] == "checked_in"
    assert response.json()["start_at"] == "2026-10-20T07:00:00+08:00"
    assert response.json()["checked_in_at"] == "2026-10-20T06:50:00+08:00"


def test_midnight_reservation_checks_in_with_code_shown_before_midnight(client, db, clock):
    """00:00 开始的预约在前一天 23:50 签到，屏幕上此时显示的是前一天的码。"""
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=at_hour(DAY, 24))
    clock.move_to(at_hour(DAY, 24) - timedelta(minutes=10))
    screen = client.get(
        f"/api/v1/seat/rooms/{room.id}/checkin-code",
        headers=user_headers(settings, perms=["seat:checkin_code"]),
    ).json()

    response = _check_in(client, user_headers(settings, perms=["seat:reserve"]), reservation, screen["code"])

    assert screen["valid_date"] == DAY.isoformat()
    assert response.status_code == 200


def test_checkin_succeeds_at_window_opening(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START - timedelta(minutes=15))

    response = _check_in(client, as_student, reservation)

    assert response.status_code == 200
    db.expire_all()
    row = db.get(Reservation, reservation.id)
    assert row.status == "checked_in"
    assert row.checked_in_at == START - timedelta(minutes=15)


def test_checkin_rejects_just_before_window_opens(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START - timedelta(minutes=15, seconds=1))

    response = _check_in(client, as_student, reservation)

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_WINDOW_CLOSED"


def test_checkin_succeeds_just_before_deadline(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START + timedelta(minutes=15) - timedelta(seconds=1))

    assert _check_in(client, as_student, reservation).status_code == 200


def test_checkin_rejects_exact_deadline(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START + timedelta(minutes=15))

    response = _check_in(client, as_student, reservation)

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_WINDOW_CLOSED"


def test_checkin_rejects_wrong_code(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START)

    response = _check_in(client, as_student, reservation, "654321")

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_CODE_INVALID"


def test_checkin_rejects_other_users_reservation(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, user_id=9999)
    _code(db, room)
    clock.move_to(START)

    assert _check_in(client, as_student, reservation).status_code == 404


def test_checkin_rejects_non_booked_reservation(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, status="cancelled")
    _code(db, room)
    clock.move_to(START)

    response = _check_in(client, as_student, reservation)

    assert response.status_code == 409
    assert response.json()["code"] == "RESERVATION_STATE_CONFLICT"


def test_second_checkin_is_rejected(client, db, clock, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    clock.move_to(START)

    first = _check_in(client, as_student, reservation)
    second = _check_in(client, as_student, reservation)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "RESERVATION_STATE_CONFLICT"


def test_checkin_rejected_after_seat_disabled(client, db, clock, as_student, as_room_admin):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat)
    _code(db, room)
    client.patch(
        f"/api/v1/seat/seats/{seat.id}", json={"status": "disabled"}, headers=as_room_admin
    ).raise_for_status()
    clock.move_to(START)

    response = _check_in(client, as_student, reservation)

    assert response.status_code == 409
    assert response.json()["code"] == "RESERVATION_STATE_CONFLICT"
