"""M1 数据模型（schema: m1）。

空间与座位主数据由 M1 唯一维护，M2/M3 只通过接口引用 room_id。
座位"不可用"有三种来源，全部可追溯：
  - M1_RESERVATION：个人预约（reservations 表）
  - M2_OCCUPY / M3_MAINTENANCE：整室占用或维修下架（room_blocks 表，source + ref_id）
每次状态变化另写一条 seat_status_logs，供追溯与验收。
"""

from datetime import date, datetime

from campus_common.db import make_metadata
from campus_common.infra_models import IdempotencyKeyMixin, OutboxMixin, ParamMixin, TimestampMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    metadata = make_metadata(settings.db_schema)


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("building", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    building: Mapped[str] = mapped_column(String(50))
    floor: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(20))  # classroom | library | other
    dept_id: Mapped[int | None] = mapped_column(Integer)  # 为空表示全校开放
    capacity: Mapped[int] = mapped_column(Integer)
    is_study_room: Mapped[bool] = mapped_column(Boolean, default=True)
    is_whole_bookable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="enabled")  # enabled | disabled


class RoomOpenHour(Base):
    __tablename__ = "room_open_hours"
    __table_args__ = (
        UniqueConstraint("room_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("open_hour >= 0 AND close_hour <= 24 AND open_hour < close_hour", name="hours"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = 周一
    open_hour: Mapped[int] = mapped_column(Integer)
    close_hour: Mapped[int] = mapped_column(Integer)


class Seat(TimestampMixin, Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("room_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    outlet: Mapped[str] = mapped_column(String(10), default="none")  # none | fixed | rail
    status: Mapped[str] = mapped_column(String(20), default="enabled")


ACTIVE_RESERVATION = text("status IN ('booked', 'checked_in')")


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="time_order"),
        # 同一座位、时段重叠的有效预约由数据库直接拒绝，两人同时抢座也只会成功一个
        ExcludeConstraint(
            (text("seat_id"), "="),
            (text("tstzrange(start_at, end_at)"), "&&"),
            name="no_seat_overlap",
            using="gist",
            where=ACTIVE_RESERVATION,
        ),
        # 同一用户同一时段只能有一个有效预约
        ExcludeConstraint(
            (text("user_id"), "="),
            (text("tstzrange(start_at, end_at)"), "&&"),
            name="no_user_overlap",
            using="gist",
            where=ACTIVE_RESERVATION,
        ),
        Index("ix_reservations_status_start", "status", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # booked | checked_in | completed | cancelled | no_show
    status: Mapped[str] = mapped_column(String(20), default="booked")
    # USER | NO_CHECK_IN | BLOCKED_BY_M2 | BLOCKED_BY_M3
    cancel_reason: Mapped[str | None] = mapped_column(String(30))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_before_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_late_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoomBlock(Base):
    """M2 整室占用 / M3 维修下架。(source, ref_id) 唯一，重复写入天然幂等。"""

    __tablename__ = "room_blocks"
    __table_args__ = (UniqueConstraint("source", "ref_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # M2_OCCUPY | M3_MAINTENANCE
    ref_id: Mapped[int] = mapped_column(Integer)  # M2 申请 ID / M3 工单 ID
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 维修中为空
    reason: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(50))  # 调用方服务名
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SeatStatusLog(Base):
    """座位状态变化流水，记录写入来源，供 GET /seats/{id}/status-history 追溯。"""

    __tablename__ = "seat_status_logs"
    __table_args__ = (Index("ix_seat_status_logs_seat_at", "seat_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state: Mapped[str] = mapped_column(String(20))  # reserved | released | blocked | unblocked
    source: Mapped[str] = mapped_column(String(20))  # M1_RESERVATION | M1_ADMIN | M2_OCCUPY | M3_MAINTENANCE
    ref_id: Mapped[int] = mapped_column(Integer)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckinCode(Base):
    __tablename__ = "checkin_codes"

    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    valid_date: Mapped[date] = mapped_column(Date, primary_key=True)
    code: Mapped[str] = mapped_column(String(12))


class Setting(ParamMixin, Base):
    """可调系统参数，结构与默认值见 schemas 中的参数模型，读写用 campus_common.params。"""

    __tablename__ = "settings"


class Outbox(OutboxMixin, Base):
    __tablename__ = "outbox"


class IdempotencyKey(IdempotencyKeyMixin, Base):
    __tablename__ = "idempotency_keys"
