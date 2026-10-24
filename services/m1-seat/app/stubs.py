"""阶段 0 的桩数据：让调用方在真实实现完成前就能对接。

实现某个接口时，把路由里对 stubs 的调用替换成真实逻辑；全部替换完后删除本文件。
"""

from datetime import timedelta

from campus_common.timeutil import at_hour, now

from app import schemas as s

ROOM = s.Room(
    id=1,
    building="第三教学楼",
    floor=1,
    name="H3106",
    type="classroom",
    dept_id=None,
    capacity=60,
    is_study_room=True,
    is_whole_bookable=True,
    open_hours=[s.OpenHour(weekday=d, open_hour=8, close_hour=22) for d in range(7)],
    status="enabled",
)
SEATS = [
    s.Seat(id=1, room_id=1, code="A-01", outlet="fixed", status="enabled"),
    s.Seat(id=2, room_id=1, code="A-02", outlet="none", status="enabled"),
    s.Seat(id=3, room_id=1, code="A-03", outlet="rail", status="enabled"),
]


def reservation(user_id: int = 1001, id_: int = 1, status: s.ReservationStatus = "booked"):
    day = now().date() + timedelta(days=1)
    return s.Reservation(
        id=id_,
        user_id=user_id,
        seat_id=1,
        room_id=1,
        start_at=at_hour(day, 14),
        end_at=at_hour(day, 16),
        status=status,
    )


def reservation_detail(user_id: int = 1001) -> s.ReservationDetail:
    return s.ReservationDetail(**reservation(user_id).model_dump(), seat=SEATS[0], room=ROOM)


def checkin_code(room_id: int) -> s.CheckinCodeOut:
    return s.CheckinCodeOut(
        room_id=room_id,
        code="483920",
        qr_payload=f"campus://checkin/{room_id}/483920",
        valid_date=now().date(),
    )


def availability() -> list[s.SeatAvailability]:
    return [
        s.SeatAvailability(
            seat_id=seat.id,
            hours=[s.HourState(hour=h, state="free") for h in range(8, 22)],
        )
        for seat in SEATS
    ]


def usage() -> s.UsageStats:
    return s.UsageStats(
        utilization=0.62,
        no_show_rate=0.08,
        by_room=[s.RoomUsage(room_id=1, utilization=0.62, no_show_rate=0.08, reservations=120)],
        by_hour={h: 0.5 for h in range(8, 22)},
    )


def status_history() -> list[s.StatusHistoryItem]:
    t = now()
    return [
        s.StatusHistoryItem(at=t, state="blocked", source="M3_MAINTENANCE", ref_id=7, start_at=t, end_at=None)
    ]
