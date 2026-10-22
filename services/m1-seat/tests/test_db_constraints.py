"""数据库层的并发保证。去掉迁移脚本里的 ExcludeConstraint 并重放迁移，这些测试必须失败。"""

from datetime import date

import pytest
from app.models import Reservation, Room, Seat
from campus_common.timeutil import at_hour
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.db
DAY = date(2026, 10, 20)


def _room_with_seats(db, n=2):
    room = Room(building="三教", floor=1, name="H3106", type="classroom", capacity=60)
    db.add(room)
    db.flush()
    seats = [Seat(room_id=room.id, code=f"A-{i}") for i in range(n)]
    db.add_all(seats)
    db.flush()
    return room, seats


def _reserve(db, room, seat, user_id, start, end, status="booked"):
    r = Reservation(
        user_id=user_id,
        seat_id=seat.id,
        room_id=room.id,
        start_at=at_hour(DAY, start),
        end_at=at_hour(DAY, end),
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def test_same_seat_overlapping_rejected(db):
    room, (seat, _) = _room_with_seats(db)
    _reserve(db, room, seat, user_id=1, start=14, end=16)
    with pytest.raises(IntegrityError, match="no_seat_overlap"):
        _reserve(db, room, seat, user_id=2, start=15, end=17)


def test_adjacent_slots_allowed(db):
    room, (seat, _) = _room_with_seats(db)
    _reserve(db, room, seat, user_id=1, start=14, end=16)
    _reserve(db, room, seat, user_id=2, start=16, end=18)  # 区间左闭右开，不重叠


def test_cancelled_reservation_frees_seat(db):
    room, (seat, _) = _room_with_seats(db)
    _reserve(db, room, seat, user_id=1, start=14, end=16, status="cancelled")
    _reserve(db, room, seat, user_id=2, start=14, end=16)


def test_same_user_cannot_hold_two_seats_at_once(db):
    room, (a, b) = _room_with_seats(db)
    _reserve(db, room, a, user_id=1, start=14, end=16)
    with pytest.raises(IntegrityError, match="no_user_overlap"):
        _reserve(db, room, b, user_id=1, start=15, end=16)
