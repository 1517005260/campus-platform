"""每日签到码和预约签到。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
import time_machine
from app.main import app
from app.models import CheckinCode, Reservation, Room, Seat
from campus_common.timeutil import BIZ_TZ
from fastapi.testclient import TestClient
from sqlalchemy import func, select

pytestmark = pytest.mark.db
BASE = datetime.now(BIZ_TZ).replace(second=0, microsecond=0) + timedelta(minutes=5)


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
    start_at: datetime,
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


def _code(db, room: Room, value: str, valid_date=BASE.date()) -> None:
    db.add(CheckinCode(room_id=room.id, valid_date=valid_date, code=value))
    db.commit()


def test_checkin_code_is_stable_and_has_qr_payload(client, db, as_screen):
    room, _ = _room_with_seat(db)
    with time_machine.travel(BASE, tick=False):
        first = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)
        second = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(first.json()["code"]) == 6
    assert first.json()["code"].isdigit()
    assert first.json()["qr_payload"] == f"campus://checkin/{room.id}/{first.json()['code']}"
    assert db.scalar(select(func.count()).select_from(CheckinCode)) == 1


def test_checkin_code_generation_is_concurrency_safe(db, as_screen):
    room, _ = _room_with_seat(db)

    def fetch():
        with TestClient(app) as concurrent_client:
            return concurrent_client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_screen)

    with time_machine.travel(BASE, tick=False), ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: fetch(), range(2)))

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["code"] == responses[1].json()["code"]
    assert db.scalar(select(func.count()).select_from(CheckinCode)) == 1


def test_checkin_code_requires_screen_permission(client, db, as_student):
    room, _ = _room_with_seat(db)
    response = client.get(f"/api/v1/seat/rooms/{room.id}/checkin-code", headers=as_student)
    assert response.status_code == 403


def test_checkin_code_rejects_unknown_room(client, db, as_screen):
    response = client.get("/api/v1/seat/rooms/999/checkin-code", headers=as_screen)
    assert response.status_code == 404


def test_checkin_succeeds_inside_window(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE + timedelta(minutes=10))
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "checked_in"
    db.expire_all()
    row = db.get(Reservation, reservation.id)
    assert row.status == "checked_in"
    assert row.checked_in_at is not None


def test_checkin_rejects_too_early(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE + timedelta(minutes=20))
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_WINDOW_CLOSED"


def test_checkin_rejects_exact_deadline(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE)
    _code(db, room, "123456")

    with time_machine.travel(BASE + timedelta(minutes=15), tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_WINDOW_CLOSED"


def test_checkin_rejects_wrong_code(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE + timedelta(minutes=10))
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "654321"},
            headers=as_student,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "CHECKIN_CODE_INVALID"


def test_checkin_rejects_other_users_reservation(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE + timedelta(minutes=10), user_id=9999)
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert response.status_code == 404


def test_checkin_rejects_non_booked_reservation(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(
        db,
        room,
        seat,
        start_at=BASE + timedelta(minutes=10),
        status="cancelled",
    )
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        response = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert response.status_code == 409
    assert response.json()["code"] == "RESERVATION_STATE_CONFLICT"


def test_second_checkin_is_rejected(client, db, as_student):
    room, seat = _room_with_seat(db)
    reservation = _reserve(db, room, seat, start_at=BASE + timedelta(minutes=10))
    _code(db, room, "123456")

    with time_machine.travel(BASE, tick=False):
        first = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )
        second = client.post(
            f"/api/v1/seat/reservations/{reservation.id}/check-in",
            json={"code": "123456"},
            headers=as_student,
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "RESERVATION_STATE_CONFLICT"
