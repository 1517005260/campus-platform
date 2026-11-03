"""座位搜索、按小时可用性和状态历史。"""

from datetime import date

import pytest
from app.models import Reservation, Room, RoomBlock, RoomOpenHour, Seat, SeatStatusLog
from campus_common.timeutil import at_hour, now

pytestmark = pytest.mark.db
DAY = date(2026, 10, 20)


def _room(
    db,
    *,
    name: str,
    dept_id: int | None = None,
    status: str = "enabled",
    open_hour: int = 8,
    close_hour: int = 22,
    seats: list[tuple[str, str, str]] | None = None,
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
        status=status,
    )
    db.add(room)
    db.flush()
    db.add(
        RoomOpenHour(
            room_id=room.id,
            weekday=DAY.weekday(),
            open_hour=open_hour,
            close_hour=close_hour,
        )
    )
    rows = [
        Seat(room_id=room.id, code=code, outlet=outlet, status=seat_status)
        for code, outlet, seat_status in (seats or [("A-01", "none", "enabled")])
    ]
    db.add_all(rows)
    db.commit()
    return room, rows


def _reserve(db, room: Room, seat: Seat, start_hour: int, end_hour: int, status: str = "booked"):
    row = Reservation(
        user_id=100,
        seat_id=seat.id,
        room_id=room.id,
        start_at=at_hour(DAY, start_hour),
        end_at=at_hour(DAY, end_hour),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def _block(db, room: Room, start_hour: int, end_hour: int | None, *, released: bool = False):
    row = RoomBlock(
        room_id=room.id,
        source="M3_MAINTENANCE",
        ref_id=room.id,
        start_at=at_hour(DAY, start_hour),
        end_at=at_hour(DAY, end_hour) if end_hour is not None else None,
        reason="维修",
        created_by="m3-repair",
        released_at=now() if released else None,
    )
    db.add(row)
    db.commit()
    return row


def test_search_returns_only_available_seats(client, db, as_student):
    room, (free, reserved, rail) = _room(
        db,
        name="H3101",
        seats=[
            ("A-01", "none", "enabled"),
            ("A-02", "none", "enabled"),
            ("A-03", "rail", "enabled"),
        ],
    )
    _reserve(db, room, reserved, 9, 11)
    blocked_room, _ = _room(db, name="H3102")
    _block(db, blocked_room, 10, 12)
    _room(db, name="H3103", dept_id=2)
    _room(db, name="H3104", status="disabled")

    response = client.get(
        "/api/v1/seat/seats/search",
        params={"date": DAY.isoformat(), "start_hour": 10, "end_hour": 11},
        headers=as_student,
    )

    assert response.status_code == 200
    assert {item["seat"]["id"] for item in response.json()["items"]} == {free.id, rail.id}
    assert response.json()["total"] == 2


def test_search_filters_by_outlet_and_room(client, db, as_student):
    first_room, _ = _room(
        db,
        name="H3101",
        seats=[("A-01", "none", "enabled"), ("A-02", "rail", "enabled")],
    )
    second_room, _ = _room(db, name="H3102", seats=[("B-01", "rail", "enabled")])

    rail = client.get(
        "/api/v1/seat/seats/search",
        params={"date": DAY.isoformat(), "start_hour": 10, "end_hour": 11, "outlet": "rail"},
        headers=as_student,
    )
    by_room = client.get(
        "/api/v1/seat/seats/search",
        params={
            "date": DAY.isoformat(),
            "start_hour": 10,
            "end_hour": 11,
            "room_id": second_room.id,
        },
        headers=as_student,
    )

    assert len(rail.json()["items"]) == 2
    assert {item["room"]["id"] for item in rail.json()["items"]} == {first_room.id, second_room.id}
    assert [item["seat"]["code"] for item in by_room.json()["items"]] == ["B-01"]


def test_search_allows_adjacent_and_released_blocks(client, db, as_student):
    room, (seat,) = _room(db, name="H3101")
    _reserve(db, room, seat, 8, 10)
    _block(db, room, 10, 11, released=True)

    response = client.get(
        "/api/v1/seat/seats/search",
        params={"date": DAY.isoformat(), "start_hour": 10, "end_hour": 11},
        headers=as_student,
    )

    assert response.status_code == 200
    assert [item["seat"]["id"] for item in response.json()["items"]] == [seat.id]


def test_search_rejects_outside_open_hours(client, db, as_student):
    _room(db, name="H3101", open_hour=8, close_hour=22)
    response = client.get(
        "/api/v1/seat/seats/search",
        params={"date": DAY.isoformat(), "start_hour": 7, "end_hour": 8},
        headers=as_student,
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_search_rejects_reversed_hours(client, db, as_student):
    response = client.get(
        "/api/v1/seat/seats/search",
        params={"date": DAY.isoformat(), "start_hour": 12, "end_hour": 10},
        headers=as_student,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TIME_RANGE"


def test_hourly_availability_includes_reserved_blocked_closed_and_free(client, db, as_student):
    room, (first, second) = _room(
        db,
        name="H3101",
        open_hour=8,
        close_hour=10,
        seats=[("A-01", "none", "enabled"), ("A-02", "none", "enabled")],
    )
    _reserve(db, room, first, 9, 10)
    _block(db, room, 8, 9)

    response = client.get(
        f"/api/v1/seat/rooms/{room.id}/availability",
        params={"date": DAY.isoformat()},
        headers=as_student,
    )

    assert response.status_code == 200
    rows = {row["seat_id"]: row["hours"] for row in response.json()}
    assert rows[first.id][0]["state"] == "closed"
    assert rows[first.id][8] == {"hour": 8, "state": "blocked", "source": "M3_MAINTENANCE"}
    assert rows[first.id][9] == {"hour": 9, "state": "reserved", "source": "M1_RESERVATION"}
    assert rows[first.id][10]["state"] == "closed"
    assert rows[second.id][8]["state"] == "blocked"
    assert rows[second.id][9]["state"] == "free"


def test_hourly_availability_marks_disabled_seat_blocked(client, db, as_room_admin):
    room, (seat,) = _room(
        db,
        name="H3101",
        seats=[("A-01", "none", "disabled")],
    )
    response = client.get(
        f"/api/v1/seat/rooms/{room.id}/availability",
        params={"date": DAY.isoformat()},
        headers=as_room_admin,
    )
    assert response.status_code == 200
    assert response.json()[0]["seat_id"] == seat.id
    assert response.json()[0]["hours"][8] == {"hour": 8, "state": "blocked", "source": "M1_ADMIN"}


def test_room_availability_hides_other_department(client, db, as_student):
    room, _ = _room(db, name="H3101", dept_id=2)
    response = client.get(
        f"/api/v1/seat/rooms/{room.id}/availability",
        params={"date": DAY.isoformat()},
        headers=as_student,
    )
    assert response.status_code == 404


def test_status_history_returns_source_and_reference(client, db, as_room_admin):
    room, (seat,) = _room(db, name="H3101")
    db.add_all(
        [
            SeatStatusLog(
                seat_id=seat.id,
                at=at_hour(DAY, 8),
                state="reserved",
                source="M1_RESERVATION",
                ref_id=11,
                start_at=at_hour(DAY, 8),
                end_at=at_hour(DAY, 10),
            ),
            SeatStatusLog(
                seat_id=seat.id,
                at=at_hour(DAY, 9),
                state="blocked",
                source="M3_MAINTENANCE",
                ref_id=22,
                start_at=at_hour(DAY, 9),
                end_at=None,
            ),
        ]
    )
    db.commit()

    response = client.get(f"/api/v1/seat/seats/{seat.id}/status-history", headers=as_room_admin)

    assert response.status_code == 200
    assert [(row["source"], row["ref_id"]) for row in response.json()] == [
        ("M3_MAINTENANCE", 22),
        ("M1_RESERVATION", 11),
    ]


def test_status_history_requires_management_permission(client, db, as_student):
    room, (seat,) = _room(db, name="H3101")
    response = client.get(f"/api/v1/seat/seats/{seat.id}/status-history", headers=as_student)
    assert response.status_code == 403
