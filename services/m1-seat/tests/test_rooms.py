"""教室、开放时间和座位主数据行为。"""

import pytest
from app.models import Room, RoomOpenHour, Seat, SeatStatusLog
from sqlalchemy import func, select

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


def test_list_rooms_filters_department_and_disabled_for_students(client, db, as_student):
    global_room = _room(db, name="GLOBAL")
    own_dept = _room(db, name="OWN", dept_id=1)
    _room(db, name="OTHER", dept_id=2)
    _room(db, name="DISABLED", status="disabled")

    response = client.get("/api/v1/seat/rooms", headers=as_student)

    assert response.status_code == 200
    assert {row["id"] for row in response.json()["items"]} == {global_room.id, own_dept.id}
    assert response.json()["total"] == 2


def test_room_manager_sees_all_rooms(client, db, as_room_admin):
    rooms = [
        _room(db, name="GLOBAL"),
        _room(db, name="OTHER", dept_id=2),
        _room(db, name="DISABLED", status="disabled"),
    ]

    response = client.get("/api/v1/seat/rooms", headers=as_room_admin)

    assert response.status_code == 200
    assert {row["id"] for row in response.json()["items"]} == {room.id for room in rooms}


def test_room_detail_hides_other_department(client, db, as_student):
    hidden = _room(db, name="OTHER", dept_id=2, seats=2)
    response = client.get(f"/api/v1/seat/rooms/{hidden.id}", headers=as_student)
    assert response.status_code == 404


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
