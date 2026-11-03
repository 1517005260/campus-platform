"""教室、开放时间和座位主数据。"""

from collections.abc import Sequence

from campus_common.auth import CurrentUser
from campus_common.errors import AppError, not_found
from campus_common.pagination import Page, PageParams, page_of
from campus_common.timeutil import now
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import Room, RoomOpenHour, Seat, SeatStatusLog


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) or str(exc.orig)


def _open_hours(models: Sequence[RoomOpenHour]) -> list[s.OpenHour]:
    return [
        s.OpenHour(weekday=row.weekday, open_hour=row.open_hour, close_hour=row.close_hour)
        for row in sorted(models, key=lambda row: row.weekday)
    ]


def _room_out(room: Room, hours: Sequence[RoomOpenHour]) -> s.Room:
    return s.Room(
        id=room.id,
        building=room.building,
        floor=room.floor,
        name=room.name,
        type=room.type,
        dept_id=room.dept_id,
        capacity=room.capacity,
        is_study_room=room.is_study_room,
        is_whole_bookable=room.is_whole_bookable,
        open_hours=_open_hours(hours),
        status=room.status,
    )


def _can_manage(user: CurrentUser) -> bool:
    return user.has("seat:room_manage")


def _visible(room: Room, user: CurrentUser) -> bool:
    if _can_manage(user):
        return True
    if room.status != "enabled":
        return False
    return room.dept_id is None or room.dept_id == user.dept_id


def _validate_hours(hours: Sequence[s.OpenHour]) -> None:
    weekdays = [row.weekday for row in hours]
    if len(weekdays) != len(set(weekdays)):
        raise AppError(400, "INVALID_OPEN_HOURS", "同一星期不能配置多条开放时间")


async def _hours_by_room(session: AsyncSession, room_ids: Sequence[int]) -> dict[int, list[RoomOpenHour]]:
    if not room_ids:
        return {}
    rows = (
        await session.scalars(
            select(RoomOpenHour)
            .where(RoomOpenHour.room_id.in_(room_ids))
            .order_by(RoomOpenHour.room_id, RoomOpenHour.weekday)
        )
    ).all()
    result: dict[int, list[RoomOpenHour]] = {room_id: [] for room_id in room_ids}
    for row in rows:
        result[row.room_id].append(row)
    return result


async def _room_detail(session: AsyncSession, room: Room) -> s.RoomDetail:
    hours = (
        await session.scalars(
            select(RoomOpenHour).where(RoomOpenHour.room_id == room.id).order_by(RoomOpenHour.weekday)
        )
    ).all()
    seats = (
        await session.scalars(select(Seat).where(Seat.room_id == room.id).order_by(Seat.code, Seat.id))
    ).all()
    return s.RoomDetail(
        **_room_out(room, hours).model_dump(),
        seats=[s.Seat.model_validate(seat, from_attributes=True) for seat in seats],
    )


async def list_rooms(
    session: AsyncSession,
    user: CurrentUser,
    *,
    building: str | None,
    type: s.RoomType | None,
    is_study_room: bool | None,
    is_whole_bookable: bool | None,
    params: PageParams,
) -> Page[s.Room]:
    conditions = []
    if building is not None:
        conditions.append(Room.building == building)
    if type is not None:
        conditions.append(Room.type == type)
    if is_study_room is not None:
        conditions.append(Room.is_study_room.is_(is_study_room))
    if is_whole_bookable is not None:
        conditions.append(Room.is_whole_bookable.is_(is_whole_bookable))
    if not _can_manage(user):
        conditions.append(Room.status == "enabled")
        conditions.append(or_(Room.dept_id.is_(None), Room.dept_id == user.dept_id))

    statement = select(Room).where(*conditions)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rooms = (
        await session.scalars(
            statement.order_by(Room.building, Room.name, Room.id).offset(params.offset).limit(params.size)
        )
    ).all()
    hours = await _hours_by_room(session, [room.id for room in rooms])
    return page_of([_room_out(room, hours[room.id]) for room in rooms], total or 0, params)


async def get_room(session: AsyncSession, user: CurrentUser, room_id: int) -> s.RoomDetail:
    room = await session.get(Room, room_id)
    if room is None or not _visible(room, user):
        raise not_found("教室", room_id)
    return await _room_detail(session, room)


async def create_room(session: AsyncSession, body: s.RoomCreate) -> s.Room:
    _validate_hours(body.open_hours)
    room = Room(
        building=body.building,
        floor=body.floor,
        name=body.name,
        type=body.type,
        dept_id=body.dept_id,
        capacity=body.capacity,
        is_study_room=body.is_study_room,
        is_whole_bookable=body.is_whole_bookable,
    )
    try:
        async with session.begin():
            session.add(room)
            await session.flush()
            session.add_all(
                [
                    RoomOpenHour(
                        room_id=room.id,
                        weekday=row.weekday,
                        open_hour=row.open_hour,
                        close_hour=row.close_hour,
                    )
                    for row in body.open_hours
                ]
            )
    except IntegrityError as exc:
        if "uq_rooms_building_name" in (_constraint_name(exc) or ""):
            raise AppError(409, "ROOM_ALREADY_EXISTS", "同一楼宇中的教室名称不能重复") from exc
        raise
    return await _reload_room(session, room.id)


async def update_room(session: AsyncSession, room_id: int, body: s.RoomUpdate) -> s.Room:
    if "open_hours" in body.model_fields_set and body.open_hours is not None:
        _validate_hours(body.open_hours)
    try:
        async with session.begin():
            room = await session.scalar(select(Room).where(Room.id == room_id).with_for_update())
            if room is None:
                raise not_found("教室", room_id)
            fields = body.model_fields_set
            before_status = room.status
            for field in (
                "building",
                "floor",
                "name",
                "type",
                "capacity",
                "is_study_room",
                "is_whole_bookable",
                "status",
            ):
                if field in fields:
                    setattr(room, field, getattr(body, field))
            if "dept_id" in fields:
                room.dept_id = body.dept_id
            if "open_hours" in fields and body.open_hours is not None:
                await session.execute(delete(RoomOpenHour).where(RoomOpenHour.room_id == room_id))
                session.add_all(
                    [
                        RoomOpenHour(
                            room_id=room_id,
                            weekday=row.weekday,
                            open_hour=row.open_hour,
                            close_hour=row.close_hour,
                        )
                        for row in body.open_hours
                    ]
                )
            if room.status != before_status:
                await _log_room_status(session, room, room.status)
            await session.flush()
    except IntegrityError as exc:
        constraint = _constraint_name(exc) or ""
        if "uq_rooms_building_name" in constraint:
            raise AppError(409, "ROOM_ALREADY_EXISTS", "同一楼宇中的教室名称不能重复") from exc
        raise
    return await _reload_room(session, room_id)


async def create_seat(session: AsyncSession, room_id: int, body: s.SeatCreate) -> s.Seat:
    seat = Seat(room_id=room_id, code=body.code, outlet=body.outlet)
    try:
        async with session.begin():
            room = await session.get(Room, room_id)
            if room is None:
                raise not_found("教室", room_id)
            session.add(seat)
            await session.flush()
    except IntegrityError as exc:
        if "uq_seats_room_id_code" in (_constraint_name(exc) or ""):
            raise AppError(409, "SEAT_ALREADY_EXISTS", "同一教室中的座位编号不能重复") from exc
        raise
    return s.Seat.model_validate(seat, from_attributes=True)


async def update_seat(session: AsyncSession, seat_id: int, body: s.SeatUpdate) -> s.Seat:
    async with session.begin():
        seat = await session.scalar(select(Seat).where(Seat.id == seat_id).with_for_update())
        if seat is None:
            raise not_found("座位", seat_id)
        fields = body.model_fields_set
        before_status = seat.status
        if "outlet" in fields and body.outlet is not None:
            seat.outlet = body.outlet
        if "status" in fields and body.status is not None:
            seat.status = body.status
        if seat.status != before_status:
            session.add(
                SeatStatusLog(
                    seat_id=seat.id,
                    at=now(),
                    state="blocked" if seat.status == "disabled" else "unblocked",
                    source="M1_ADMIN",
                    ref_id=seat.id,
                    start_at=None,
                    end_at=None,
                )
            )
        await session.flush()
    return s.Seat.model_validate(seat, from_attributes=True)


async def _log_room_status(session: AsyncSession, room: Room, status: str) -> None:
    seat_ids = (await session.scalars(select(Seat.id).where(Seat.room_id == room.id))).all()
    at = now()
    for seat_id in seat_ids:
        session.add(
            SeatStatusLog(
                seat_id=seat_id,
                at=at,
                state="blocked" if status == "disabled" else "unblocked",
                source="M1_ADMIN",
                ref_id=room.id,
                start_at=None,
                end_at=None,
            )
        )


async def _reload_room(session: AsyncSession, room_id: int) -> s.Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise not_found("教室", room_id)
    hours = (await session.scalars(select(RoomOpenHour).where(RoomOpenHour.room_id == room_id))).all()
    return _room_out(room, hours)
