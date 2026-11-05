"""M1 运营统计。"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from campus_common.errors import AppError, not_found
from campus_common.timeutil import at_hour, to_biz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import Reservation, Room, RoomBlock, RoomOpenHour, Seat
from app.shared import overlaps

UTILIZED_STATUSES = ("checked_in", "completed")
CLOSED_STATUSES = ("no_show", "completed")


def _clip(start: datetime, end: datetime, lower: datetime, upper: datetime):
    clipped_start = max(start, lower)
    clipped_end = min(end, upper)
    if clipped_start >= clipped_end:
        return None
    return clipped_start, clipped_end


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        current_start, current_end = merged[-1]
        if start <= current_end:
            merged[-1] = (current_start, max(current_end, end))
        else:
            merged.append((start, end))
    return merged


def _subtract(
    intervals: list[tuple[datetime, datetime]],
    cuts: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    result = _merge(intervals)
    for cut_start, cut_end in _merge(cuts):
        next_result = []
        for start, end in result:
            intersection = _clip(start, end, cut_start, cut_end)
            if intersection is None:
                next_result.append((start, end))
                continue
            if start < intersection[0]:
                next_result.append((start, intersection[0]))
            if intersection[1] < end:
                next_result.append((intersection[1], end))
        result = next_result
    return result


def _seconds_by_hour(intervals: list[tuple[datetime, datetime]]) -> dict[int, float]:
    totals: dict[int, float] = defaultdict(float)
    for start, end in intervals:
        cursor = start
        while cursor < end:
            local_cursor = to_biz(cursor)
            next_hour = at_hour(local_cursor.date(), local_cursor.hour + 1)
            segment_end = min(end, next_hour)
            totals[local_cursor.hour] += (segment_end - cursor).total_seconds()
            cursor = segment_end
    return dict(totals)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator > 0 else 0.0


def _open_intervals(
    room: Room,
    hours: dict[int, RoomOpenHour],
    date_from: date,
    date_to: date,
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    if room.status != "enabled" or not room.is_study_room:
        return []
    result = []
    day = date_from
    while day <= date_to:
        open_hour = hours.get(day.weekday())
        if open_hour is not None:
            start = max(at_hour(day, open_hour.open_hour), range_start)
            end = min(at_hour(day, open_hour.close_hour), range_end)
            if start < end:
                result.append((start, end))
        day += timedelta(days=1)
    return _merge(result)


def _block_intervals(
    blocks: list[tuple[datetime, datetime | None]],
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    intervals = []
    for start_at, effective_end in blocks:
        clipped = _clip(start_at, effective_end or range_end, range_start, range_end)
        if clipped is not None:
            intervals.append(clipped)
    return _merge(intervals)


def _reservation_intervals(
    reservations: list[Reservation],
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    intervals = []
    for reservation in reservations:
        if reservation.status not in UTILIZED_STATUSES:
            continue
        clipped = _clip(reservation.start_at, reservation.end_at, range_start, range_end)
        if clipped is not None:
            intervals.append(clipped)
    # 不同座位在同一时刻都可能被使用，不能把各座位预约合并成一个区间。
    return intervals


async def usage_stats(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    room_id: int | None,
) -> s.UsageStats:
    if date_to < date_from:
        raise AppError(400, "INVALID_DATE_RANGE", "结束日期不能早于开始日期")
    range_start = at_hour(date_from, 0)
    range_end = at_hour(date_to + timedelta(days=1), 0)

    statement = select(Room).where(Room.is_study_room.is_(True)).order_by(Room.id)
    if room_id is not None:
        room = await session.get(Room, room_id)
        if room is None:
            raise not_found("教室", room_id)
        rooms = [room]
    else:
        rooms = list((await session.scalars(statement)).all())
    room_ids = [room.id for room in rooms]
    if not room_ids:
        return s.UsageStats(
            utilization=0.0, no_show_rate=0.0, by_room=[], by_hour={h: 0.0 for h in range(24)}
        )

    seats_rows = (
        await session.scalars(select(Seat).where(Seat.room_id.in_(room_ids), Seat.status == "enabled"))
    ).all()
    reservations = (
        await session.scalars(
            select(Reservation).where(
                Reservation.room_id.in_(room_ids),
                overlaps(Reservation.start_at, Reservation.end_at, range_start, range_end),
            )
        )
    ).all()
    # 占用在释放时刻或计划结束时刻（取较早者，都为空表示仍在占用）之前扣除开放时间；已释放的历史占用同样扣除
    effective_end = func.least(RoomBlock.released_at, RoomBlock.end_at)
    blocks = (
        await session.execute(
            select(RoomBlock.room_id, RoomBlock.start_at, effective_end).where(
                RoomBlock.room_id.in_(room_ids),
                overlaps(RoomBlock.start_at, effective_end, range_start, range_end),
            )
        )
    ).all()

    hours_by_room = {room.id: {row.weekday: row for row in room.open_hours} for room in rooms}
    seat_count = defaultdict(int)
    for seat in seats_rows:
        seat_count[seat.room_id] += 1
    reservations_by_room: dict[int, list[Reservation]] = defaultdict(list)
    for row in reservations:
        reservations_by_room[row.room_id].append(row)
    blocks_by_room: dict[int, list[tuple[datetime, datetime | None]]] = defaultdict(list)
    for block_room_id, start_at, end_at in blocks:
        blocks_by_room[block_room_id].append((start_at, end_at))

    by_room: list[s.RoomUsage] = []
    total_utilized = 0.0
    total_open = 0.0
    total_no_show = 0
    total_closed = 0
    total_utilized_by_hour: dict[int, float] = defaultdict(float)
    total_open_by_hour: dict[int, float] = defaultdict(float)

    for room in rooms:
        open_intervals = _open_intervals(
            room,
            hours_by_room[room.id],
            date_from,
            date_to,
            range_start,
            range_end,
        )
        blocks_for_room = _block_intervals(blocks_by_room[room.id], range_start, range_end)
        effective_open = _subtract(open_intervals, blocks_for_room)
        utilized_intervals = []
        for interval in _reservation_intervals(reservations_by_room[room.id], range_start, range_end):
            utilized_intervals.extend(
                clipped
                for effective in effective_open
                if (clipped := _clip(interval[0], interval[1], effective[0], effective[1])) is not None
            )

        utilized_by_hour = _seconds_by_hour(utilized_intervals)
        open_by_hour = {
            hour: seconds * seat_count[room.id] for hour, seconds in _seconds_by_hour(effective_open).items()
        }
        utilized_seconds = sum(utilized_by_hour.values())
        open_seconds = sum(open_by_hour.values())
        room_reservations = reservations_by_room[room.id]
        no_show = sum(row.status == "no_show" for row in room_reservations)
        closed = sum(row.status in CLOSED_STATUSES for row in room_reservations)
        by_room.append(
            s.RoomUsage(
                room_id=room.id,
                utilization=_ratio(utilized_seconds, open_seconds),
                no_show_rate=_ratio(no_show, closed),
                reservations=len(room_reservations),
            )
        )

        total_utilized += utilized_seconds
        total_open += open_seconds
        total_no_show += no_show
        total_closed += closed
        for hour in range(24):
            total_utilized_by_hour[hour] += utilized_by_hour.get(hour, 0.0)
            total_open_by_hour[hour] += open_by_hour.get(hour, 0.0)

    return s.UsageStats(
        utilization=_ratio(total_utilized, total_open),
        no_show_rate=_ratio(total_no_show, total_closed),
        by_room=by_room,
        by_hour={
            hour: _ratio(total_utilized_by_hour.get(hour, 0.0), total_open_by_hour.get(hour, 0.0))
            for hour in range(24)
        },
    )
