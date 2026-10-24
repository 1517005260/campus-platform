"""M3 接口契约。"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

OrderStatus = Literal["submitted", "dispatched", "in_progress", "pending_acceptance", "closed", "cancelled"]


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None


class OrderCreate(BaseModel):
    room_id: int
    seat_id: int | None = Field(None, description="具体座位；为空表示教室整体问题")
    category: str = Field(examples=["空调", "照明", "桌椅", "插座", "网络"])
    description: str = Field(min_length=2, max_length=1000)
    photos: list[str] = Field(default_factory=list, description="图片 URL")


class TimelineItem(BaseModel):
    at: AwareDatetime
    actor: UserBrief | None
    action: str
    from_status: OrderStatus | None
    to_status: OrderStatus | None
    note: str | None


class WorkOrder(BaseModel):
    id: int
    reporter: UserBrief
    room_id: int
    seat_id: int | None
    category: str
    description: str
    photos: list[str]
    status: OrderStatus
    blocks_room: bool = Field(description="维修中是否下架整间教室")
    assignee: UserBrief | None
    deadline_at: AwareDatetime | None
    escalation_level: int = Field(description="0 表示未升级，每超时一次 +1")
    rating: int | None
    timeline: list[TimelineItem]


class CancelRequest(BaseModel):
    reason: str = Field(max_length=200)


class DispatchRequest(BaseModel):
    assignee_id: int
    deadline_at: AwareDatetime
    blocks_room: bool = Field(False, description="开始维修时是否下架整间教室")


class CompleteRequest(BaseModel):
    note: str = Field(max_length=1000)
    photos: list[str] = Field(default_factory=list)


class AcceptRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=500)


class RejectAcceptanceRequest(BaseModel):
    reason: str = Field(max_length=500)


class EscalationRule(BaseModel):
    status: Literal["dispatched", "in_progress", "pending_acceptance"]
    timeout_hours: int = Field(ge=1)
    notify_perm: str = Field("repair:manage", description="升级时通知拥有该权限的人")


class RepairSettings(BaseModel):
    categories: list[str] = ["空调", "照明", "桌椅", "插座", "网络", "其他"]
    escalation_rules: list[EscalationRule] = [
        EscalationRule(status="dispatched", timeout_hours=24),
        EscalationRule(status="in_progress", timeout_hours=72),
        EscalationRule(status="pending_acceptance", timeout_hours=72),
    ]
    admin_accept_after_hours: int = Field(72, description="报修人超过该时长未验收，管理员可代验收")
