"""种子数据（幂等，约定见 campus_common.seeding）。

- 基础数据（所有环境）：预约参数默认值。
- 演示数据（SEED_DEMO=true）：演示教室、开放时间与座位，使用固定 ID。
"""

from campus_common.params import seed_params
from campus_common.seeding import reset_sequences, run_seed
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.models import Room, RoomOpenHour, Seat, Setting
from app.schemas import SeatSettings

DEMO_ROOMS = [
    dict(
        id=1,
        building="第三教学楼",
        floor=1,
        name="H3106",
        type="classroom",
        dept_id=None,
        capacity=60,
        is_study_room=True,
        is_whole_bookable=True,
    ),
    dict(
        id=2,
        building="光华楼",
        floor=2,
        name="图书馆自习室 A",
        type="library",
        dept_id=None,
        capacity=80,
        is_study_room=True,
        is_whole_bookable=False,
    ),
    dict(
        id=3,
        building="计算机楼",
        floor=3,
        name="CS-301",
        type="classroom",
        dept_id=1,
        capacity=40,
        is_study_room=True,
        is_whole_bookable=True,
    ),
]


def seed_base(session) -> None:
    seed_params(session, Setting, SeatSettings())


def seed_demo(session) -> None:
    """开放时间与座位只随新写入的教室一起写入；已存在或被占用 ID 的教室不改动。"""
    new_rooms = session.scalars(
        insert(Room).values(DEMO_ROOMS).on_conflict_do_nothing().returning(Room.id)
    ).all()
    if new_rooms:
        hours = [
            dict(id=room_id * 10 + d, room_id=room_id, weekday=d, open_hour=8, close_hour=22)
            for room_id in new_rooms
            for d in range(7)
        ]
        session.execute(insert(RoomOpenHour).values(hours).on_conflict_do_nothing())
        outlets = ["fixed", "none", "rail", "none"]
        seats = [
            dict(id=room_id * 100 + i, room_id=room_id, code=f"A-{i:02d}", outlet=outlets[i % 4])
            for room_id in new_rooms
            for i in range(1, 13)
        ]
        session.execute(insert(Seat).values(seats).on_conflict_do_nothing())
    reset_sequences(session, settings.db_schema, ["rooms", "room_open_hours", "seats"])


if __name__ == "__main__":
    run_seed(settings, seed_base, seed_demo)
