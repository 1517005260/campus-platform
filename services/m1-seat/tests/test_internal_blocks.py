"""跨模块占用、释放和内部查询的行为测试。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app.main import app
from app.models import Outbox, Reservation, Room, RoomBlock, RoomOpenHour, Seat, SeatStatusLog, Violation
from campus_common.testing import service_headers
from campus_common.timeutil import at_hour
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import DAY, M2_KEY, M3_KEY

pytestmark = pytest.mark.db


def _seed_room(db, *, seats: int = 2, name: str = "H3106") -> tuple[Room, list[Seat]]:
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
        [RoomOpenHour(room_id=room.id, weekday=weekday, open_hour=8, close_hour=22) for weekday in range(7)]
    )
    rows = [Seat(room_id=room.id, code=f"A-{index:02d}") for index in range(1, seats + 1)]
    db.add_all(rows)
    db.commit()
    return room, rows


def _reserve(
    db,
    room: Room,
    seat: Seat,
    *,
    user_id: int,
    start_hour: int,
    end_hour: int,
    status: str = "booked",
) -> Reservation:
    reservation = Reservation(
        user_id=user_id,
        seat_id=seat.id,
        room_id=room.id,
        start_at=at_hour(DAY, start_hour),
        end_at=at_hour(DAY, end_hour),
        status=status,
    )
    db.add(reservation)
    db.commit()
    return reservation


def _block_body(room: Room, *, source: str = "M3_MAINTENANCE", ref_id: int = 7):
    return {
        "room_id": room.id,
        "start_at": at_hour(DAY, 10).isoformat(),
        "end_at": at_hour(DAY, 12).isoformat(),
        "source": source,
        "ref_id": ref_id,
        "reason": "空调维修",
    }


def _count(db, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


def _payload(db, event_type: str, reservation_id: int) -> dict:
    """某个预约对应的一条 outbox 消息的 payload。"""
    payloads = [
        row.envelope["payload"] for row in db.scalars(select(Outbox).where(Outbox.type == event_type))
    ]
    matched = [
        p
        for p in payloads
        if p.get("reservation_id", p.get("params", {}).get("reservation_id")) == reservation_id
    ]
    assert len(matched) == 1, payloads
    return matched[0]


def test_create_block_cancels_overlapping_reservations_and_records_sources(client, db, as_m3):
    room, seats = _seed_room(db)
    overlapped = _reserve(db, room, seats[0], user_id=41, start_hour=9, end_hour=11)
    contained = _reserve(db, room, seats[1], user_id=42, start_hour=11, end_hour=13)
    adjacent = _reserve(db, room, seats[0], user_id=43, start_hour=13, end_hour=14)

    response = client.post(
        "/internal/v1/blocks",
        json=_block_body(room),
        headers={**as_m3, "X-Request-ID": "req-block-create"},
    )

    assert response.status_code == 200
    assert {row["id"] for row in response.json()["cancelled_reservations"]} == {overlapped.id, contained.id}
    db.expire_all()
    assert db.get(Reservation, overlapped.id).status == "cancelled"
    assert db.get(Reservation, contained.id).status == "cancelled"
    assert db.get(Reservation, overlapped.id).cancel_reason == "BLOCKED_BY_M3"
    assert db.get(Reservation, adjacent.id).status == "booked"
    assert _count(db, Violation) == 0
    assert _count(db, RoomBlock) == 1
    assert _count(
        db,
        SeatStatusLog,
        SeatStatusLog.state == "blocked",
        SeatStatusLog.source == "M3_MAINTENANCE",
        SeatStatusLog.ref_id == 7,
    ) == len(seats)
    assert (
        _count(
            db,
            SeatStatusLog,
            SeatStatusLog.state == "released",
            SeatStatusLog.source == "M1_RESERVATION",
        )
        == 2
    )
    types = list(db.scalars(select(Outbox.type)))
    assert types.count("notification.send") == 2
    assert types.count("m1.reservation.cancelled") == 2
    assert types.count("audit.record") == 1
    notification = _payload(db, "notification.send", overlapped.id)
    assert notification["user_ids"] == [41]
    assert notification["template"] == "seat.reservation_cancelled_by_block"
    assert notification["params"] == {
        "reservation_id": overlapped.id,
        "start_at": "2026-10-20T09:00:00+08:00",
        "end_at": "2026-10-20T11:00:00+08:00",
        "block_source": "M3_MAINTENANCE",
        "block_ref_id": 7,
        "reason": "空调维修",
    }
    assert _payload(db, "m1.reservation.cancelled", overlapped.id) == {
        "reservation_id": overlapped.id,
        "user_id": 41,
        "reason": "BLOCKED",
    }
    audit = db.scalar(select(Outbox).where(Outbox.type == "audit.record"))
    assert audit.envelope["request_id"] == "req-block-create"
    assert audit.envelope["payload"]["actor_id"] == "m3-repair"


def test_same_idempotency_key_returns_first_result_once(client, db, as_m3):
    room, seat = _seed_room(db, seats=1)
    reservation = _reserve(db, room, seat[0], user_id=41, start_hour=10, end_hour=11)
    body = _block_body(room)

    first = client.post("/internal/v1/blocks", json=body, headers=as_m3)
    second = client.post("/internal/v1/blocks", json=body, headers=as_m3)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["cancelled_reservations"][0]["id"] == reservation.id
    assert _count(db, RoomBlock) == 1
    assert _count(db, Outbox) == 3


def test_concurrent_requests_with_same_key_create_one_block(db, as_m3):
    room, seat = _seed_room(db, seats=1)
    reservation = _reserve(db, room, seat[0], user_id=41, start_hour=10, end_hour=11)
    body = _block_body(room)

    def send():
        with TestClient(app) as concurrent_client:
            return concurrent_client.post("/internal/v1/blocks", json=body, headers=as_m3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(), range(2)))

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["cancelled_reservations"][0]["id"] == reservation.id
    assert _count(db, RoomBlock) == 1
    assert _count(db, Outbox) == 3


def test_same_key_with_different_body_is_rejected(client, db, as_m3):
    room, _ = _seed_room(db)
    first = _block_body(room)
    second = {**first, "reason": "另一个原因"}

    assert client.post("/internal/v1/blocks", json=first, headers=as_m3).status_code == 200
    response = client.post("/internal/v1/blocks", json=second, headers=as_m3)

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_same_source_reference_with_another_key_returns_existing_block(client, db, as_m3):
    room, _ = _seed_room(db)
    body = _block_body(room)
    first = client.post("/internal/v1/blocks", json=body, headers=as_m3)
    other_key = service_headers("m3-repair", M3_KEY, idempotency_key="m3-order-7-block-retry")
    second = client.post("/internal/v1/blocks", json=body, headers=other_key)

    assert first.status_code == second.status_code == 200
    assert second.json() == {"block_id": first.json()["block_id"], "cancelled_reservations": []}
    assert _count(db, RoomBlock) == 1


def test_same_source_reference_with_different_request_is_rejected(client, db, as_m3):
    room, _ = _seed_room(db)
    body = _block_body(room)
    assert client.post("/internal/v1/blocks", json=body, headers=as_m3).status_code == 200
    other_key = service_headers("m3-repair", M3_KEY, idempotency_key="m3-order-7-block-v2")

    response = client.post(
        "/internal/v1/blocks",
        json={**body, "end_at": at_hour(DAY, 13).isoformat()},
        headers=other_key,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "BLOCK_REFERENCE_CONFLICT"
    assert _count(db, RoomBlock) == 1


def test_concurrent_requests_with_different_keys_create_one_block(db):
    room, seat = _seed_room(db, seats=1)
    reservation = _reserve(db, room, seat[0], user_id=41, start_hour=10, end_hour=11)
    body = _block_body(room)

    def send(key: str):
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(
                "/internal/v1/blocks", json=body, headers=service_headers("m3-repair", M3_KEY, key)
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, [f"m3-order-7-block-{i}" for i in range(4)]))

    assert [response.status_code for response in responses] == [200] * 4
    assert len({response.json()["block_id"] for response in responses}) == 1
    cancelled = [response.json()["cancelled_reservations"] for response in responses]
    assert sorted(len(rows) for rows in cancelled) == [0, 0, 0, 1]
    assert _count(db, RoomBlock) == 1
    assert _count(db, Outbox, Outbox.type == "m1.reservation.cancelled") == 1
    db.expire_all()
    assert db.get(Reservation, reservation.id).status == "cancelled"


def test_reposting_released_block_follows_idempotency_then_lifecycle(client, db, as_m3):
    """M3 的幂等键固定为 m3-order-{工单号}-block：同键重发是重放首次结果；只有换了键才会碰到已释放的单号。"""
    room, (seat, _) = _seed_room(db)
    earlier = _reserve(db, room, seat, user_id=40, start_hour=10, end_hour=11)
    body = _block_body(room)
    first = client.post("/internal/v1/blocks", json=body, headers=as_m3)
    assert [row["id"] for row in first.json()["cancelled_reservations"]] == [earlier.id]
    assert client.delete("/internal/v1/blocks/M3_MAINTENANCE/7", headers=as_m3).json() == {"released": True}
    later = _reserve(db, room, seat, user_id=41, start_hour=10, end_hour=11)

    replay = client.post("/internal/v1/blocks", json=body, headers=as_m3)
    reused = client.post("/internal/v1/blocks", json={**body, "reason": "再次维修"}, headers=as_m3)
    new_key = client.post(
        "/internal/v1/blocks",
        json=body,
        headers=service_headers("m3-repair", M3_KEY, idempotency_key="m3-order-7-block-2"),
    )

    assert (replay.status_code, replay.json()) == (200, first.json())
    assert (reused.status_code, reused.json()["code"]) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert (new_key.status_code, new_key.json()["code"]) == (409, "BLOCK_ALREADY_RELEASED")
    db.expire_all()
    assert db.get(Reservation, later.id).status == "booked"
    assert db.scalar(select(RoomBlock.released_at)) is not None
    assert _count(db, RoomBlock) == 1


def test_m2_occupation_cancels_with_m2_reason(client, db):
    room, (seat, _) = _seed_room(db)
    reservation = _reserve(db, room, seat, user_id=41, start_hour=10, end_hour=11)
    headers = service_headers("m2-room", M2_KEY, idempotency_key="m2-app-9-occupy")

    response = client.post(
        "/internal/v1/blocks", json=_block_body(room, source="M2_OCCUPY", ref_id=9), headers=headers
    )

    assert response.status_code == 200
    assert response.json()["cancelled_reservations"][0]["cancel_reason"] == "BLOCKED_BY_M2"
    db.expire_all()
    assert db.get(Reservation, reservation.id).cancel_reason == "BLOCKED_BY_M2"
    assert (
        _count(db, SeatStatusLog, SeatStatusLog.state == "blocked", SeatStatusLog.source == "M2_OCCUPY") == 2
    )
    assert _payload(db, "notification.send", reservation.id)["params"]["block_source"] == "M2_OCCUPY"


def test_service_cannot_release_another_modules_block(client, db, as_m3):
    room, _ = _seed_room(db)
    assert client.post("/internal/v1/blocks", json=_block_body(room), headers=as_m3).status_code == 200

    response = client.delete(
        "/internal/v1/blocks/M3_MAINTENANCE/7", headers=service_headers("m2-room", M2_KEY)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "BLOCK_SOURCE_FORBIDDEN"
    db.expire_all()
    assert db.scalar(select(RoomBlock.released_at)) is None


def test_release_block_is_idempotent_and_writes_unblocked_logs(client, db, as_m3):
    room, seats = _seed_room(db)
    created = client.post("/internal/v1/blocks", json=_block_body(room), headers=as_m3)
    assert created.status_code == 200

    first = client.delete("/internal/v1/blocks/M3_MAINTENANCE/7", headers=as_m3)
    second = client.delete("/internal/v1/blocks/M3_MAINTENANCE/7", headers=as_m3)

    assert first.json() == {"released": True}
    assert second.json() == {"released": False}
    db.expire_all()
    block = db.scalar(select(RoomBlock).where(RoomBlock.source == "M3_MAINTENANCE"))
    assert block.released_at is not None
    assert _count(
        db,
        SeatStatusLog,
        SeatStatusLog.state == "unblocked",
        SeatStatusLog.source == "M3_MAINTENANCE",
        SeatStatusLog.ref_id == 7,
    ) == len(seats)
    assert _count(db, Outbox, Outbox.type == "audit.record") == 2


def test_block_only_cancels_reservations_that_overlap(client, db, as_m3):
    room, seat = _seed_room(db, seats=1)
    before = _reserve(db, room, seat[0], user_id=41, start_hour=8, end_hour=10)
    inside = _reserve(db, room, seat[0], user_id=42, start_hour=10, end_hour=12)
    after = _reserve(db, room, seat[0], user_id=43, start_hour=12, end_hour=14)

    response = client.post("/internal/v1/blocks", json=_block_body(room), headers=as_m3)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["cancelled_reservations"]] == [inside.id]
    db.expire_all()
    assert db.get(Reservation, before.id).status == "booked"
    assert db.get(Reservation, inside.id).status == "cancelled"
    assert db.get(Reservation, after.id).status == "booked"


def test_open_ended_block_cancels_all_future_overlaps(client, db, as_m3):
    room, seat = _seed_room(db, seats=1)
    past = _reserve(db, room, seat[0], user_id=41, start_hour=8, end_hour=10)
    future = _reserve(db, room, seat[0], user_id=42, start_hour=14, end_hour=15)
    body = _block_body(room)
    body["end_at"] = None

    response = client.post("/internal/v1/blocks", json=body, headers=as_m3)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["cancelled_reservations"]] == [future.id]
    db.expire_all()
    assert db.get(Reservation, past.id).status == "booked"
    assert db.get(Reservation, future.id).status == "cancelled"


def test_service_cannot_use_another_modules_block_source(client, db, as_m2):
    room, _ = _seed_room(db)
    response = client.post(
        "/internal/v1/blocks",
        json=_block_body(room),
        headers=as_m2,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "BLOCK_SOURCE_FORBIDDEN"


def test_internal_get_room_returns_open_hours_and_all_seats(client, db, as_m3):
    room, seats = _seed_room(db)
    _seed_room(db, seats=1, name="H3107")  # 另一间教室的座位不在其中
    seats[1].status = "disabled"
    db.commit()

    response = client.get(f"/internal/v1/rooms/{room.id}", headers=as_m3)

    assert response.status_code == 200
    assert response.json()["id"] == room.id
    assert len(response.json()["open_hours"]) == 7
    assert [seat["id"] for seat in response.json()["seats"]] == [seat.id for seat in seats]


def test_internal_room_reservations_filters_active_and_overlapping(client, db, as_m2):
    room, seats = _seed_room(db)
    booked = _reserve(db, room, seats[0], user_id=41, start_hour=9, end_hour=11)
    checked_in = _reserve(db, room, seats[1], user_id=42, start_hour=10, end_hour=12, status="checked_in")
    _reserve(db, room, seats[0], user_id=43, start_hour=9, end_hour=11, status="cancelled")
    _reserve(db, room, seats[1], user_id=44, start_hour=12, end_hour=13, status="booked")

    response = client.get(
        f"/internal/v1/rooms/{room.id}/reservations",
        params={
            "start_at": at_hour(DAY, 9).isoformat(),
            "end_at": at_hour(DAY, 12).isoformat(),
        },
        headers=as_m2,
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [booked.id, checked_in.id]
    assert response.json()[0]["start_at"] == "2026-10-20T09:00:00+08:00"


def test_internal_room_reservations_rejects_reversed_range(client, db, as_m2):
    room, _ = _seed_room(db)
    response = client.get(
        f"/internal/v1/rooms/{room.id}/reservations",
        params={"start_at": at_hour(DAY, 12).isoformat(), "end_at": at_hour(DAY, 9).isoformat()},
        headers=as_m2,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_internal_violation_count_includes_since_boundary(client, db):
    room, seat = _seed_room(db, seats=1)
    since = at_hour(DAY - timedelta(days=1), 0)
    created = {
        "before": since - timedelta(microseconds=1),
        "at": since,
        "after": at_hour(DAY, 12),
        "other_user": at_hour(DAY, 12),
    }
    for hour, (name, created_at) in enumerate(created.items(), start=8):
        user_id = 43 if name == "other_user" else 42
        row = _reserve(
            db, room, seat[0], user_id=user_id, start_hour=hour, end_hour=hour + 1, status="no_show"
        )
        db.add(Violation(user_id=user_id, reservation_id=row.id, created_at=created_at))
    db.commit()

    response = client.get(
        "/internal/v1/users/42/violations",
        params={"since": since.isoformat()},
        headers=service_headers("m2-room", M2_KEY),
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 42, "count": 2}
