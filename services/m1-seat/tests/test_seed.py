"""演示种子数据：可重复运行，已存在或被占用 ID 的教室不改动，也不为它写开放时间与座位。"""

import pytest
from app.models import Room, RoomOpenHour, Seat
from app.seed import DEMO_ROOMS, seed_demo
from sqlalchemy import func, select

pytestmark = pytest.mark.db


@pytest.fixture
def db_seed():
    return seed_demo


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_seed_demo_is_repeatable(db):
    before = (count(db, Room), count(db, RoomOpenHour), count(db, Seat))
    seed_demo(db)
    db.commit()
    assert (count(db, Room), count(db, RoomOpenHour), count(db, Seat)) == before == (3, 21, 36)


def test_seed_demo_skips_room_whose_name_is_taken(db):
    first = DEMO_ROOMS[0]
    db.query(Seat).filter_by(room_id=first["id"]).delete()
    db.query(RoomOpenHour).filter_by(room_id=first["id"]).delete()
    db.query(Room).filter_by(id=first["id"]).delete()
    db.add(Room(**{**first, "id": 50}))
    db.commit()
    seed_demo(db)
    db.commit()
    assert db.get(Room, first["id"]) is None
    assert count(db, Seat) == 24
    assert count(db, RoomOpenHour) == 14
