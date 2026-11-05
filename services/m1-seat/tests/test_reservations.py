"""预约创建、取消、历史、复订和违约记录。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app.config import settings
from app.main import app
from app.models import (
    Outbox,
    Reservation,
    Room,
    RoomBlock,
    RoomOpenHour,
    Seat,
    SeatStatusLog,
    Setting,
    Violation,
)
from campus_common.testing import user_headers
from campus_common.timeutil import at_hour, now
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import DAY

pytestmark = pytest.mark.db


def _room(
    db,
    *,
    name: str = "H3101",
    dept_id: int | None = None,
    room_status: str = "enabled",
    seat_status: str = "enabled",
    seats: int = 1,
) -> tuple[Room, list[Seat]]:
    room = Room(
        building="第三教学楼",
        floor=1,
        name=name,
        type="classroom",
        dept_id=dept_id,
        capacity=60,
        is_study_room=True,
        is_whole_bookable=True,
        status=room_status,
    )
    db.add(room)
    db.flush()
    db.add_all(
        [RoomOpenHour(room_id=room.id, weekday=weekday, open_hour=8, close_hour=22) for weekday in range(7)]
    )
    rows = [Seat(room_id=room.id, code=f"A-{index:02d}", status=seat_status) for index in range(1, seats + 1)]
    db.add_all(rows)
    db.commit()
    return room, rows


def _body(start_hour: int = 14, end_hour: int = 16) -> dict:
    return {"date": DAY.isoformat(), "start_hour": start_hour, "end_hour": end_hour}


def _reserve(
    db,
    room: Room,
    seat: Seat,
    *,
    user_id: int = 1001,
    start_hour: int = 14,
    end_hour: int = 16,
    status: str = "booked",
) -> Reservation:
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


def _count(db, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


def test_create_reservation_records_source_log(client, db, as_student):
    _, (seat,) = _room(db)

    response = client.post(
        "/api/v1/seat/reservations", json={**_body(), "seat_id": seat.id}, headers=as_student
    )

    assert response.status_code == 201
    assert response.json()["seat_id"] == seat.id
    db.expire_all()
    reservation = db.get(Reservation, response.json()["id"])
    assert reservation.status == "booked"
    log = db.scalar(select(SeatStatusLog).where(SeatStatusLog.ref_id == reservation.id))
    assert (log.state, log.source) == ("reserved", "M1_RESERVATION")


def test_create_reservation_uses_configured_max_hours(client, db, as_student):
    _, (seat,) = _room(db)
    db.add(Setting(key="max_hours", value=2))
    db.commit()

    response = client.post(
        "/api/v1/seat/reservations",
        json={**_body(10, 13), "seat_id": seat.id},
        headers=as_student,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DURATION"


def _create(client, headers, seat: Seat, start_hour: int, end_hour: int):
    return client.post(
        "/api/v1/seat/reservations", json={**_body(start_hour, end_hour), "seat_id": seat.id}, headers=headers
    )


def test_create_reservation_accepts_exactly_max_hours(client, db, as_student):
    _, (seat,) = _room(db)
    assert _create(client, as_student, seat, 10, 14).status_code == 201
    response = _create(client, as_student, seat, 14, 19)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DURATION"


def test_create_reservation_accepts_open_and_close_hour_edges(client, db, as_student):
    _, (seat,) = _room(db)
    assert _create(client, as_student, seat, 8, 9).status_code == 201
    assert _create(client, as_student, seat, 21, 22).status_code == 201
    response = _create(client, as_student, seat, 20, 23)
    assert response.status_code == 400
    assert response.json()["code"] == "OUTSIDE_OPEN_HOURS"


def test_create_reservation_rejects_slot_starting_now(client, db, clock, as_student):
    _, (seat,) = _room(db)
    clock.move_to(at_hour(DAY, 13))
    response = _create(client, as_student, seat, 13, 14)
    assert response.status_code == 400
    assert response.json()["code"] == "RESERVATION_IN_PAST"
    assert _create(client, as_student, seat, 14, 15).status_code == 201


def test_reservation_times_use_business_timezone(client, db, as_student):
    _, (seat,) = _room(db)
    created = _create(client, as_student, seat, 14, 16)

    mine = client.get("/api/v1/seat/reservations/mine", headers=as_student)

    assert created.json()["start_at"] == "2026-10-20T14:00:00+08:00"
    assert mine.json()["items"][0]["start_at"] == "2026-10-20T14:00:00+08:00"
    assert mine.json()["items"][0]["end_at"] == "2026-10-20T16:00:00+08:00"


def test_create_reservation_rejects_past(client, db, as_student):
    _, (seat,) = _room(db)
    past = now() - timedelta(days=1)
    response = client.post(
        "/api/v1/seat/reservations",
        json={"date": past.date().isoformat(), "start_hour": 10, "end_hour": 11, "seat_id": seat.id},
        headers=as_student,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "RESERVATION_IN_PAST"


def test_create_reservation_rejects_outside_open_hours(client, db, as_student):
    _, (seat,) = _room(db)
    response = client.post(
        "/api/v1/seat/reservations",
        json={**_body(7, 8), "seat_id": seat.id},
        headers=as_student,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "OUTSIDE_OPEN_HOURS"


def test_create_reservation_rejects_other_department(client, db, as_student):
    _, (seat,) = _room(db, dept_id=2)
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(), "seat_id": seat.id}, headers=as_student
    )
    assert response.status_code == 403
    assert response.json()["code"] == "DEPT_RESTRICTED"


def test_create_reservation_rejects_disabled_seat(client, db, as_student):
    _, (seat,) = _room(db, seat_status="disabled")
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(), "seat_id": seat.id}, headers=as_student
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEAT_NOT_AVAILABLE"


def test_create_reservation_rejects_room_block(client, db, as_student):
    room, (seat,) = _room(db)
    db.add(
        RoomBlock(
            room_id=room.id,
            source="M3_MAINTENANCE",
            ref_id=7,
            start_at=at_hour(DAY, 10),
            end_at=at_hour(DAY, 12),
            reason="维修",
            created_by="m3-repair",
        )
    )
    db.commit()
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(11, 13), "seat_id": seat.id}, headers=as_student
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEAT_NOT_AVAILABLE"


def test_create_reservation_rejects_seat_overlap(client, db, as_student):
    room, (seat,) = _room(db)
    _reserve(db, room, seat, start_hour=15, end_hour=17)
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(14, 16), "seat_id": seat.id}, headers=as_student
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEAT_NOT_AVAILABLE"


def test_create_reservation_rejects_user_overlap(client, db, as_student):
    room, (first, second) = _room(db, seats=2)
    _reserve(db, room, first, start_hour=15, end_hour=17)
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(14, 16), "seat_id": second.id}, headers=as_student
    )
    assert response.status_code == 409
    assert response.json()["code"] == "USER_TIME_CONFLICT"


def test_create_reservation_allows_adjacent_slot(client, db, as_student):
    room, (seat,) = _room(db)
    _reserve(db, room, seat, start_hour=12, end_hour=14)
    response = client.post(
        "/api/v1/seat/reservations", json={**_body(14, 16), "seat_id": seat.id}, headers=as_student
    )
    assert response.status_code == 201


def test_concurrent_reservations_only_one_succeeds(db):
    _, (seat,) = _room(db)
    first = user_headers(settings, perms=["seat:reserve"], user_id=2001, dept_id=1)
    second = user_headers(settings, perms=["seat:reserve"], user_id=2002, dept_id=1)

    def send(headers):
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(
                "/api/v1/seat/reservations",
                json={**_body(), "seat_id": seat.id},
                headers=headers,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, [first, second]))

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert _count(db, Reservation, Reservation.seat_id == seat.id) == 1


def test_cancel_reservation_records_release_and_event(client, db, as_student):
    _, (seat,) = _room(db)
    created = client.post(
        "/api/v1/seat/reservations", json={**_body(), "seat_id": seat.id}, headers=as_student
    )
    reservation_id = created.json()["id"]

    response = client.post(f"/api/v1/seat/reservations/{reservation_id}/cancel", headers=as_student)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancel_reason"] == "USER"
    db.expire_all()
    log = db.scalar(
        select(SeatStatusLog).where(
            SeatStatusLog.seat_id == seat.id,
            SeatStatusLog.state == "released",
        )
    )
    assert log is not None
    assert db.scalar(select(Outbox.type).where(Outbox.type == "m1.reservation.cancelled")) is not None


def test_cannot_cancel_another_users_reservation(client, db, as_student):
    room, (seat,) = _room(db)
    reservation = _reserve(db, room, seat, user_id=9999)
    response = client.post(f"/api/v1/seat/reservations/{reservation.id}/cancel", headers=as_student)
    assert response.status_code == 404


def test_cannot_cancel_started_reservation(client, db, as_student):
    room, (seat,) = _room(db)
    reservation = Reservation(
        user_id=1001,
        seat_id=seat.id,
        room_id=room.id,
        start_at=now() - timedelta(hours=1),
        end_at=now() + timedelta(hours=1),
        status="booked",
    )
    db.add(reservation)
    db.commit()

    response = client.post(f"/api/v1/seat/reservations/{reservation.id}/cancel", headers=as_student)
    assert response.status_code == 409
    assert response.json()["code"] == "RESERVATION_STATE_CONFLICT"


def test_history_filters_and_returns_details(client, db, as_student):
    room, (seat,) = _room(db)
    completed = _reserve(db, room, seat, start_hour=8, end_hour=10, status="completed")
    _reserve(db, room, seat, start_hour=10, end_hour=12, status="no_show")
    _reserve(db, room, seat, start_hour=12, end_hour=14, status="cancelled")

    response = client.get(
        "/api/v1/seat/reservations/mine",
        params={"status": "completed"},
        headers=as_student,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == completed.id
    assert response.json()["items"][0]["seat"]["id"] == seat.id
    assert response.json()["items"][0]["room"]["id"] == room.id


def test_rebook_creates_new_reservation_for_same_seat(client, db, as_student):
    room, (seat,) = _room(db)
    previous = _reserve(db, room, seat, start_hour=8, end_hour=10, status="completed")

    response = client.post(
        f"/api/v1/seat/reservations/{previous.id}/rebook",
        json=_body(18, 20),
        headers=as_student,
    )

    assert response.status_code == 201
    assert response.json()["id"] != previous.id
    assert response.json()["seat_id"] == seat.id
    assert response.json()["status"] == "booked"


def test_cannot_rebook_another_users_history(client, db, as_student):
    room, (seat,) = _room(db)
    previous = _reserve(db, room, seat, user_id=9999, status="completed")
    response = client.post(
        f"/api/v1/seat/reservations/{previous.id}/rebook",
        json=_body(18, 20),
        headers=as_student,
    )
    assert response.status_code == 404


def test_my_violations_returns_only_current_user(client, db, as_student):
    room, seats = _room(db, seats=2)
    own = _reserve(db, room, seats[0], start_hour=8, end_hour=9, status="no_show")
    other = _reserve(db, room, seats[1], user_id=2002, start_hour=10, end_hour=11, status="no_show")
    db.add_all(
        [Violation(user_id=1001, reservation_id=own.id), Violation(user_id=2002, reservation_id=other.id)]
    )
    db.commit()

    response = client.get("/api/v1/seat/violations/mine", headers=as_student)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["reservation_id"] == own.id
