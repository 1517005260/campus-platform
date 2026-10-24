"""跨模块消息契约。

消息统一发布到 topic exchange `campus.events`，路由键即 type。
本文件是消息契约的代码形式，contracts/events/asyncapi.yaml 是它的文档形式，两者一起评审。
改动 payload 只能加可选字段；要做不兼容改动就新建 version=2 的类型。
"""

import uuid
from typing import Any, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, Field

from campus_common.timeutil import now

EXCHANGE = "campus.events"
DEAD_LETTER_EXCHANGE = "campus.events.dlx"


class Envelope(BaseModel):
    message_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    version: int = 1
    occurred_at: AwareDatetime = Field(default_factory=now)
    producer: str
    request_id: str | None = None
    payload: dict[str, Any]


class Ref(BaseModel):
    """消息或通知关联的业务对象，例如 {module: "m3", type: "work_order", id: 7}。"""

    module: Literal["common", "m1", "m2", "m3"]
    type: str
    id: int


# ---- notification.send：任何服务 → common ----
class NotificationSend(BaseModel):
    TYPE: ClassVar[str] = "notification.send"
    user_ids: list[int]
    template: str = Field(description="通知模板编码，例如 seat.remind_before")
    params: dict[str, Any] = Field(default_factory=dict, description="模板参数")
    channels: list[Literal["inapp", "email"]] = ["inapp", "email"]
    ref: Ref | None = None


# ---- audit.record：任何服务 → common ----
class AuditRecord(BaseModel):
    TYPE: ClassVar[str] = "audit.record"
    actor_type: Literal["user", "service", "system"]
    actor_id: str = Field(description="用户 ID、服务名或定时任务名")
    module: Literal["common", "m1", "m2", "m3"]
    action: str = Field(description="动作编码，例如 block.create")
    target_type: str
    target_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


# ---- 领域事件：目前没有必需的消费者，供统计和 DSH 代理订阅 ----
class ReservationCancelled(BaseModel):
    TYPE: ClassVar[str] = "m1.reservation.cancelled"
    reservation_id: int
    user_id: int
    reason: Literal["USER", "NO_SHOW", "BLOCKED"]


class ApplicationStatusChanged(BaseModel):
    TYPE: ClassVar[str] = "m2.application.status_changed"
    application_id: int
    from_status: str
    to_status: str


class WorkOrderStatusChanged(BaseModel):
    TYPE: ClassVar[str] = "m3.workorder.status_changed"
    order_id: int
    from_status: str
    to_status: str


EVENT_TYPES: dict[str, type[BaseModel]] = {
    m.TYPE: m
    for m in (
        NotificationSend,
        AuditRecord,
        ReservationCancelled,
        ApplicationStatusChanged,
        WorkOrderStatusChanged,
    )
}
