"""每个服务都有的基础设施表。各服务在自己的 models.py 里继承这些 mixin 建表，
表落在各自的 schema 中。

    class Outbox(OutboxMixin, Base): __tablename__ = "outbox"
    class Setting(ParamMixin, Base): __tablename__ = "settings"
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class OutboxMixin:
    """待发布的消息。与业务数据在同一事务写入，由 relay 任务异步投递。"""

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(100))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class TimestampMixin:
    """业务表的创建与更新时间。"""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ParamMixin:
    """可调系统参数（键值表）。读写与默认值见 campus_common.params，默认值由各服务的参数模型定义。"""

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)


class InboxMixin:
    """已处理过的消息 ID，用于消费端去重。"""

    message_id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    type: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKeyMixin:
    """服务间写接口的幂等记录：(caller, key) 唯一，重复请求返回首次结果。"""

    caller: Mapped[str] = mapped_column(String(50), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))  # 请求内容的 SHA-256，识别同键不同请求
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
