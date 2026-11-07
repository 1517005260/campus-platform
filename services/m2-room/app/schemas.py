"""M2 接口契约。"""

from typing import Literal

from campus_common.timeutil import TimeRangeModel
from pydantic import AwareDatetime, BaseModel, Field, model_validator

ApplicationStatus = Literal["pending", "approved", "rejected", "withdrawn", "expired", "cancelled"]


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None


class Eligibility(BaseModel):
    eligible: bool
    reasons: list[str] = Field(description="不满足的原因，例如 近 30 天违约 3 次")


class ApplicationCreate(TimeRangeModel):
    room_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    purpose: str = Field(min_length=2, max_length=500, examples=["班级读书会"])
    attendees: int = Field(ge=1)


class ApprovalRecordOut(BaseModel):
    level: int
    approver: UserBrief | None = Field(description="系统动作（如超时）为空")
    action: Literal["approve", "reject", "expire", "withdraw", "cancel"]
    comment: str | None
    at: AwareDatetime


class Application(BaseModel):
    id: int
    applicant: UserBrief
    room_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    purpose: str
    attendees: int
    status: ApplicationStatus
    current_level: int
    total_levels: int
    deadline_at: AwareDatetime = Field(description="当前级别审批截止时间，超时自动撤销")
    records: list[ApprovalRecordOut]


class ApplicationForApprover(Application):
    affected_reservations: int = Field(description="批准后将被取消的个人座位预约数")


class ApprovalAction(BaseModel):
    comment: str | None = Field(None, max_length=500)


class FlowLevel(BaseModel):
    level: int = Field(ge=1)
    approver_perm: str = Field("room:approve", description="审批人需具备的权限码")
    scope: Literal["dept", "school"] = Field(description="dept：申请人所在院系的审批人")
    timeout_hours: int = Field(48, ge=1)


class ApprovalFlow(BaseModel):
    name: str
    room_type: Literal["classroom", "library", "other"] | None = None
    dept_scoped: bool | None = None
    priority: int = 0
    levels: list[FlowLevel] = Field(min_length=1)

    @model_validator(mode="after")
    def levels_are_sequential(self):
        expected = list(range(1, len(self.levels) + 1))
        if [level.level for level in self.levels] != expected:
            raise ValueError("审批级别必须从 1 开始连续且按顺序排列")
        return self


class RoomSettings(BaseModel):
    max_violations: int = Field(3, ge=0, description="近 violation_window_days 天违约达到该次数不能申请")
    violation_window_days: int = Field(30, ge=1)
    advance_days_min: int = Field(1, ge=0, description="至少提前几天申请")
    advance_days_max: int = Field(30, ge=1, description="最多提前几天申请")

    @model_validator(mode="after")
    def valid_advance_window(self):
        if self.advance_days_max < self.advance_days_min:
            raise ValueError("advance_days_max 不能小于 advance_days_min")
        return self
