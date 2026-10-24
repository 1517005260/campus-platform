"""M3 数据模型（schema: m3）。位置引用 M1 的 room_id / seat_id。"""

from datetime import datetime

from campus_common.db import make_metadata
from campus_common.infra_models import OutboxMixin, ParamMixin, TimestampMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    metadata = make_metadata(settings.db_schema)


class WorkOrder(TimestampMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (Index("ix_work_orders_status_deadline", "status", "deadline_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(Integer, index=True)
    room_id: Mapped[int] = mapped_column(Integer, index=True)
    seat_id: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    photos: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # submitted | dispatched | in_progress | pending_acceptance | closed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    blocks_room: Mapped[bool] = mapped_column(Boolean, default=False)  # 派单时由调度员决定
    assignee_id: Mapped[int | None] = mapped_column(Integer, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(Integer)  # 报修人或代验收的管理员
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}


class WorkOrderEvent(Base):
    """工单时间线：每次状态变化、派单、升级都记一条。"""

    __tablename__ = "work_order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[int | None] = mapped_column(Integer)  # 系统动作为空
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)


class Setting(ParamMixin, Base):
    """可调系统参数，结构与默认值见 schemas 中的参数模型，读写用 campus_common.params。"""

    __tablename__ = "settings"


class Outbox(OutboxMixin, Base):
    __tablename__ = "outbox"
