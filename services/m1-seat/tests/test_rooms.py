"""教室、开放时间和座位主数据行为。"""

import pytest
from app.config import settings
from app.models import Outbox, Reservation, Room, RoomOpenHour, Seat, SeatStatusLog, Violation
from campus_common.testing import NOW, user_headers
from campus_common.timeutil import at_hour
from sqlalchemy import func, select

from tests.conftest import DAY

pytestmark = pytest.mark.db


def _room(
    db,
    *,
    name: str,
    dept_id: int | None = None,
    status: str = "enabled",
    seats: int = 0,
) -> Room:
    room = Room(
        building="第三教学楼",
        floor=1,
        name=name,
        type="classroom",
        dept_id=dept_id,
        capacity=60,
        is_study_room=True,
        is_whole_bookable=True,
        status=status,
    )
    db.add(room)
    db.flush()
    db.add_all(
        [RoomOpenHour(room_id=room.id, weekday=weekday, open_hour=8, close_hour=22) for weekday in range(7)]
    )
    db.add_all([Seat(room_id=room.id, code=f"A-{index:02d}") for index in range(1, seats + 1)])
    db.commit()
    return room


def _create_body(name: str = "H3201", *, dept_id: int | None = None) -> dict:
    return {
        "building": "第三教学楼",
        "floor": 3,
        "name": name,
        "type": "classroom",
        "dept_id": dept_id,
        "capacity": 40,
        "is_study_room": True,
        "is_whole_bookable": False,
        "open_hours": [
            {"weekday": 0, "open_hour": 8, "close_hour": 22},
            {"weekday": 1, "open_hour": 9, "close_hour": 21},
        ],
    }


ALL_ROOMS = {"GLOBAL", "OWN", "OTHER", "DISABLED"}


@pytest.mark.parametrize(
    ("perms", "dept_id", "visible"),
    [
        (["seat:reserve"], 1, {"GLOBAL", "OWN"}),
        (["seat:room_manage"], 1, ALL_ROOMS),
        (["seat:stats"], None, ALL_ROOMS),
        (["seat:checkin_code"], None, {"GLOBAL", "OWN", "OTHER"}),
    ],
)
def test_room_visibility_is_the_same_for_list_detail_and_availability(client, db, perms, dept_id, visible):
    rooms = {
        "GLOBAL": _room(db, name="GLOBAL"),
        "OWN": _room(db, name="OWN", dept_id=1),
        "OTHER": _room(db, name="OTHER", dept_id=2),
        "DISABLED": _room(db, name="DISABLED", status="disabled"),
    }
    headers = user_headers(settings, perms=perms, dept_id=dept_id)

    listed = client.get("/api/v1/seat/rooms", headers=headers).json()
    assert ({row["name"] for row in listed["items"]}, listed["total"]) == (visible, len(visible))
    for name, room in rooms.items():
        detail = client.get(f"/api/v1/seat/rooms/{room.id}", headers=headers)
        availability = client.get(
            f"/api/v1/seat/rooms/{room.id}/availability", params={"date": DAY.isoformat()}, headers=headers
        )
        expected = 200 if name in visible else 404
        assert (name, detail.status_code, availability.status_code) == (name, expected, expected)


def test_room_detail_returns_open_hours_and_seats(client, db, as_student):
    room = _room(db, name="GLOBAL", seats=2)
    response = client.get(f"/api/v1/seat/rooms/{room.id}", headers=as_student)
    assert response.status_code == 200
    assert len(response.json()["open_hours"]) == 7
    assert [seat["code"] for seat in response.json()["seats"]] == ["A-01", "A-02"]


def test_create_room_persists_open_hours(client, db, as_room_admin):
    response = client.post("/api/v1/seat/rooms", json=_create_body(), headers=as_room_admin)
    assert response.status_code == 201
    assert len(response.json()["open_hours"]) == 2
    db.expire_all()
    room = db.scalar(select(Room).where(Room.name == "H3201"))
    assert room is not None
    assert (
        db.scalar(select(func.count()).select_from(RoomOpenHour).where(RoomOpenHour.room_id == room.id)) == 2
    )


def test_create_room_rejects_duplicate_name(client, db, as_room_admin):
    _room(db, name="H3201")
    response = client.post("/api/v1/seat/rooms", json=_create_body(), headers=as_room_admin)
    assert response.status_code == 409
    assert response.json()["code"] == "ROOM_ALREADY_EXISTS"


def test_create_room_rejects_duplicate_weekday(client, db, as_room_admin):
    body = _create_body()
    body["open_hours"] = [
        {"weekday": 0, "open_hour": 8, "close_hour": 10},
        {"weekday": 0, "open_hour": 12, "close_hour": 14},
    ]
    response = client.post("/api/v1/seat/rooms", json=body, headers=as_room_admin)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_OPEN_HOURS"


def test_update_room_replaces_hours_and_logs_status(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=2)
    response = client.patch(
        f"/api/v1/seat/rooms/{room.id}",
        json={
            "status": "disabled",
            "open_hours": [{"weekday": 2, "open_hour": 10, "close_hour": 16}],
        },
        headers=as_room_admin,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert response.json()["open_hours"] == [{"weekday": 2, "open_hour": 10, "close_hour": 16}]
    db.expire_all()
    blocked = db.scalars(
        select(SeatStatusLog).where(
            SeatStatusLog.source == "M1_ADMIN",
            SeatStatusLog.state == "blocked",
            SeatStatusLog.ref_id == room.id,
        )
    ).all()
    assert len(blocked) == 2


def test_update_seat_changes_outlet_and_logs_disable(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=1)
    seat = db.scalar(select(Seat).where(Seat.room_id == room.id))

    response = client.patch(
        f"/api/v1/seat/seats/{seat.id}",
        json={"outlet": "rail", "status": "disabled"},
        headers=as_room_admin,
    )

    assert response.status_code == 200
    assert response.json()["outlet"] == "rail"
    assert response.json()["status"] == "disabled"
    db.expire_all()
    log = db.scalar(select(SeatStatusLog).where(SeatStatusLog.seat_id == seat.id))
    assert (log.state, log.source, log.ref_id) == ("blocked", "M1_ADMIN", seat.id)


def test_create_seat_rejects_duplicate_code(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=1)
    response = client.post(
        f"/api/v1/seat/rooms/{room.id}/seats",
        json={"code": "A-01", "outlet": "fixed"},
        headers=as_room_admin,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEAT_ALREADY_EXISTS"


def test_room_management_requires_permission(client, db, as_student):
    response = client.post("/api/v1/seat/rooms", json=_create_body(), headers=as_student)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def _reservation(db, seat: Seat, *, user_id: int, start_hour: int, end_hour: int, status: str) -> Reservation:
    row = Reservation(
        user_id=user_id,
        seat_id=seat.id,
        room_id=seat.room_id,
        start_at=at_hour(DAY, start_hour),
        end_at=at_hour(DAY, end_hour),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def _outbox_payloads(db, event_type: str) -> list[dict]:
    return [row.envelope["payload"] for row in db.scalars(select(Outbox).where(Outbox.type == event_type))]


def test_disabling_seat_cancels_unfinished_reservations_without_violation(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=2)
    seat, other_seat = db.scalars(select(Seat).where(Seat.room_id == room.id).order_by(Seat.code)).all()
    future = _reservation(db, seat, user_id=41, start_hour=14, end_hour=16, status="booked")
    ongoing = _reservation(db, seat, user_id=42, start_hour=6, end_hour=8, status="checked_in")
    ended = _reservation(db, seat, user_id=43, start_hour=4, end_hour=6, status="checked_in")
    elsewhere = _reservation(db, other_seat, user_id=44, start_hour=14, end_hour=16, status="booked")

    response = client.patch(
        f"/api/v1/seat/seats/{seat.id}", json={"status": "disabled"}, headers=as_room_admin
    )

    assert response.status_code == 200
    db.expire_all()
    for row in (future, ongoing):
        cancelled = db.get(Reservation, row.id)
        assert (cancelled.status, cancelled.cancel_reason) == ("cancelled", "ADMIN_DISABLED")
    assert db.get(Reservation, ended.id).status == "checked_in"  # end_at == 当前时刻，已经结束
    assert db.get(Reservation, elsewhere.id).status == "booked"
    assert db.scalar(select(func.count()).select_from(Violation)) == 0
    released = db.scalars(
        select(SeatStatusLog).where(SeatStatusLog.state == "released").order_by(SeatStatusLog.ref_id)
    ).all()
    assert [(log.source, log.ref_id, log.seat_id, log.at) for log in released] == [
        ("M1_ADMIN", future.id, seat.id, NOW),
        ("M1_ADMIN", ongoing.id, seat.id, NOW),
    ]
    notifications = sorted(_outbox_payloads(db, "notification.send"), key=lambda p: p["user_ids"])
    assert [(p["user_ids"], p["template"]) for p in notifications] == [
        ([41], "seat.reservation_cancelled_by_admin"),
        ([42], "seat.reservation_cancelled_by_admin"),
    ]
    assert notifications[0]["params"] == {
        "reservation_id": future.id,
        "start_at": "2026-10-20T14:00:00+08:00",
        "end_at": "2026-10-20T16:00:00+08:00",
        "cause": "seat_disabled",
    }
    assert sorted(
        (p["reservation_id"], p["user_id"], p["reason"])
        for p in _outbox_payloads(db, "m1.reservation.cancelled")
    ) == sorted([(future.id, 41, "ADMIN"), (ongoing.id, 42, "ADMIN")])


def test_disabling_room_cancels_reservations_of_all_its_seats(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=2)
    other_room = _room(db, name="H3202", seats=1)
    first, second = db.scalars(select(Seat).where(Seat.room_id == room.id).order_by(Seat.code)).all()
    (outside,) = db.scalars(select(Seat).where(Seat.room_id == other_room.id)).all()
    rows = [
        _reservation(db, first, user_id=41, start_hour=14, end_hour=16, status="booked"),
        _reservation(db, second, user_id=42, start_hour=10, end_hour=12, status="booked"),
    ]
    untouched = _reservation(db, outside, user_id=43, start_hour=14, end_hour=16, status="booked")

    response = client.patch(
        f"/api/v1/seat/rooms/{room.id}", json={"status": "disabled"}, headers=as_room_admin
    )

    assert response.status_code == 200
    db.expire_all()
    assert [db.get(Reservation, row.id).cancel_reason for row in rows] == ["ADMIN_DISABLED"] * 2
    assert db.get(Reservation, untouched.id).status == "booked"
    assert sorted(
        (p["user_ids"][0], p["params"]["cause"]) for p in _outbox_payloads(db, "notification.send")
    ) == [(41, "room_disabled"), (42, "room_disabled")]


def test_deregistering_study_room_cancels_like_disabling(client, db, as_room_admin):
    """is_study_room true → false 即注销自习室，与停用教室的处理相同；false → true 不改动预约。"""
    room = _room(db, name="H3201", seats=1)
    seat = db.scalar(select(Seat).where(Seat.room_id == room.id))
    future = _reservation(db, seat, user_id=41, start_hour=14, end_hour=16, status="booked")
    ended = _reservation(db, seat, user_id=42, start_hour=4, end_hour=6, status="checked_in")

    response = client.patch(
        f"/api/v1/seat/rooms/{room.id}", json={"is_study_room": False}, headers=as_room_admin
    )

    assert response.status_code == 200
    db.expire_all()
    cancelled = db.get(Reservation, future.id)
    assert (cancelled.status, cancelled.cancel_reason) == ("cancelled", "ADMIN_DISABLED")
    assert db.get(Reservation, ended.id).status == "checked_in"
    assert db.scalar(select(func.count()).select_from(Violation)) == 0
    log = db.scalar(select(SeatStatusLog).where(SeatStatusLog.state == "released"))
    assert (log.source, log.ref_id) == ("M1_ADMIN", future.id)
    (notification,) = _outbox_payloads(db, "notification.send")
    assert (notification["user_ids"], notification["template"], notification["params"]["cause"]) == (
        [41],
        "seat.reservation_cancelled_by_admin",
        "room_deregistered",
    )
    assert _outbox_payloads(db, "m1.reservation.cancelled") == [
        {"reservation_id": future.id, "user_id": 41, "reason": "ADMIN"}
    ]

    later = _reservation(db, seat, user_id=43, start_hour=18, end_hour=20, status="booked")
    reopened = client.patch(
        f"/api/v1/seat/rooms/{room.id}", json={"is_study_room": True}, headers=as_room_admin
    )
    assert reopened.status_code == 200
    db.expire_all()
    assert db.get(Reservation, later.id).status == "booked"


def test_disabling_and_deregistering_together_is_reported_as_room_disabled(client, db, as_room_admin):
    room = _room(db, name="H3201", seats=1)
    seat = db.scalar(select(Seat).where(Seat.room_id == room.id))
    _reservation(db, seat, user_id=41, start_hour=14, end_hour=16, status="booked")

    response = client.patch(
        f"/api/v1/seat/rooms/{room.id}",
        json={"status": "disabled", "is_study_room": False},
        headers=as_room_admin,
    )

    assert response.status_code == 200
    (notification,) = _outbox_payloads(db, "notification.send")
    assert notification["params"]["cause"] == "room_disabled"


@pytest.mark.parametrize(
    "field",
    [
        "building",
        "floor",
        "name",
        "type",
        "capacity",
        "is_study_room",
        "is_whole_bookable",
        "open_hours",
        "status",
    ],
)
def test_update_room_rejects_null_for_required_field(client, db, as_room_admin, field):
    room = _room(db, name="H3201")

    response = client.patch(f"/api/v1/seat/rooms/{room.id}", json={field: None}, headers=as_room_admin)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_room_null_dept_opens_room_and_omitted_fields_stay(client, db, as_room_admin):
    room = _room(db, name="H3201", dept_id=2)

    response = client.patch(f"/api/v1/seat/rooms/{room.id}", json={"dept_id": None}, headers=as_room_admin)

    assert response.status_code == 200
    assert (response.json()["dept_id"], response.json()["name"], len(response.json()["open_hours"])) == (
        None,
        "H3201",
        7,
    )


@pytest.mark.parametrize("field", ["building", "name"])
@pytest.mark.parametrize("value", ["", "   "])
def test_room_building_and_name_must_not_be_blank(client, db, as_room_admin, field, value):
    room = _room(db, name="H3201")

    body = _create_body("H3301") | {field: value}
    created = client.post("/api/v1/seat/rooms", json=body, headers=as_room_admin)
    updated = client.patch(f"/api/v1/seat/rooms/{room.id}", json={field: value}, headers=as_room_admin)

    assert (created.status_code, updated.status_code) == (422, 422)
    assert db.scalar(select(func.count()).select_from(Room)) == 1


def test_room_building_and_name_are_trimmed(client, db, as_room_admin):
    body = _create_body(" H3301 ") | {"building": " 第三教学楼 "}

    response = client.post("/api/v1/seat/rooms", json=body, headers=as_room_admin)

    assert response.status_code == 201, response.text
    assert (response.json()["building"], response.json()["name"]) == ("第三教学楼", "H3301")


@pytest.mark.parametrize("value", ["", "   "])
def test_seat_code_must_not_be_blank(client, db, as_room_admin, value):
    room = _room(db, name="H3201")
    response = client.post(f"/api/v1/seat/rooms/{room.id}/seats", json={"code": value}, headers=as_room_admin)
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Seat)) == 0


def test_seat_code_is_trimmed(client, db, as_room_admin):
    room = _room(db, name="H3201")
    seats = f"/api/v1/seat/rooms/{room.id}/seats"
    response = client.post(seats, json={"code": " A-09 "}, headers=as_room_admin)
    assert response.status_code == 201, response.text
    assert response.json()["code"] == "A-09"


def test_blank_names_stored_before_the_rule_still_read(client, db, as_room_admin):
    room = _room(db, name="", seats=1)
    room.building = " "
    db.add(Seat(room_id=room.id, code=""))
    db.commit()

    listed = client.get("/api/v1/seat/rooms", headers=as_room_admin)
    detail = client.get(f"/api/v1/seat/rooms/{room.id}", headers=as_room_admin)

    assert (listed.status_code, detail.status_code) == (200, 200)
    assert (listed.json()["items"][0]["building"], listed.json()["items"][0]["name"]) == (" ", "")
    assert sorted(seat["code"] for seat in detail.json()["seats"]) == ["", "A-01"]


def test_update_room_rejects_values_the_table_cannot_store(client, db, as_room_admin):
    room = _room(db, name="H3201")
    for body in ({"name": "x" * 51}, {"capacity": 0}):
        response = client.patch(f"/api/v1/seat/rooms/{room.id}", json=body, headers=as_room_admin)
        assert response.status_code == 422


@pytest.mark.parametrize("field", ["outlet", "status"])
def test_update_seat_rejects_null(client, db, as_room_admin, field):
    room = _room(db, name="H3201", seats=1)
    seat = db.scalar(select(Seat).where(Seat.room_id == room.id))

    response = client.patch(f"/api/v1/seat/seats/{seat.id}", json={field: None}, headers=as_room_admin)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
