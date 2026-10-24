"""M2 数据模型（schema: m2）。教室本身属于 M1，这里只保存 room_id。"""

from datetime import datetime
from typing import Any

from campus_common.db import make_metadata
from campus_common.infra_models import OutboxMixin, ParamMixin, TimestampMixin
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    metadata = make_metadata(settings.db_schema)


class ApprovalFlow(Base):
    """审批流配置。levels 形如 [{level, approver_perm, scope: dept|school, timeout_hours}]。"""

    __tablename__ = "approval_flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    room_type: Mapped[str | None] = mapped_column(String(20))  # 为空表示适用所有类型
    dept_scoped: Mapped[bool | None] = mapped_column()  # 是否只适用于院系教室；为空表示都适用
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 多条匹配时取最大
    levels: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="time_order"),
        Index("ix_applications_status_deadline", "status", "deadline_at"),
        Index("ix_applications_room_time", "room_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(Integer, index=True)
    applicant_dept_id: Mapped[int | None] = mapped_column(Integer)
    room_id: Mapped[int] = mapped_column(Integer)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str] = mapped_column(Text)
    attendees: Mapped[int] = mapped_column(Integer)
    # pending | approved | rejected | withdrawn | expired | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # 提交时复制审批流，之后修改配置不影响在途申请
    flow_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    current_level: Mapped[int] = mapped_column(Integer, default=1)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 当前级别审批截止
    m1_block_id: Mapped[int | None] = mapped_column(Integer)  # 审批通过后 M1 返回的占用 ID
    version: Mapped[int] = mapped_column(Integer, default=1)  # 乐观锁

    __mapper_args__ = {"version_id_col": version}


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[int | None] = mapped_column(Integer)  # 系统动作（超时）为空
    action: Mapped[str] = mapped_column(String(20))  # approve | reject | expire | withdraw | cancel
    comment: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(ParamMixin, Base):
    """可调系统参数，结构与默认值见 schemas 中的参数模型，读写用 campus_common.params。"""

    __tablename__ = "settings"


class Outbox(OutboxMixin, Base):
    __tablename__ = "outbox"
