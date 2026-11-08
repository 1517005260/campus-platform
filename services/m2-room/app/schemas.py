"""M2 接口契约。"""

from typing import Annotated, Literal

from campus_common.timeutil import TimeRangeModel
from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

ApplicationStatus = Literal["pending", "approved", "rejected", "withdrawn", "expired", "cancelled"]
ApproverPerm = Literal["room:approve", "room:approve_school"]
Scope = Literal["dept", "school"]
RecordAction = Literal["approve", "reject", "expire", "withdraw", "cancel"]

# 每级的审批权限由范围决定：院系级由本院系的 room:approve 持有人审批，学校级由 room:approve_school 持有人审批
SCOPE_PERM: dict[Scope, ApproverPerm] = {"dept": "room:approve", "school": "room:approve_school"}


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None


class Eligibility(BaseModel):
    eligible: bool
    reasons: list[str] = Field(description="不满足的原因，例如 近 30 天违约 3 次，达到上限 3 次")


class ApplicationCreate(TimeRangeModel):
    room_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    purpose: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)] = Field(
        examples=["班级读书会"]
    )
    attendees: int = Field(ge=1, description="不超过教室容量")


class ApprovalRecordOut(BaseModel):
    level: int
    approver: UserBrief | None = Field(description="系统动作（如超时）为空")
    action: RecordAction
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
    deadline_at: AwareDatetime = Field(
        description="当前级别审批截止时间；到截止时间或申请开始时仍未审批完成则自动撤销"
    )
    records: list[ApprovalRecordOut]


class ApplicationForApprover(Application):
    affected_reservations: int | None = Field(
        description="批准后将被取消的个人座位预约数；查询 M1 失败时为空（不影响待办列表）"
    )


class ApprovalAction(BaseModel):
    comment: str | None = Field(None, max_length=500)


class FlowLevel(BaseModel):
    level: int = Field(ge=1)
    approver_perm: ApproverPerm = Field(
        "room:approve",
        description="审批人需具备的权限码，须与 scope 对应：dept → room:approve，"
        "school → room:approve_school",
    )
    scope: Scope = Field(description="dept：申请人所在院系的审批人；school：全校的学校级审批人")
    timeout_hours: int = Field(48, ge=1)

    @model_validator(mode="after")
    def perm_matches_scope(self):
        if self.approver_perm != SCOPE_PERM[self.scope]:
            raise ValueError(f"scope={self.scope} 的审批级须使用权限码 {SCOPE_PERM[self.scope]}")
        return self


class ApprovalFlow(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
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


FlowList = Annotated[list[ApprovalFlow], Field(min_length=1)]


class RoomSettings(BaseModel):
    max_violations: int = Field(3, ge=0, description="近 violation_window_days 天违约达到该次数不能申请")
    violation_window_days: int = Field(30, ge=1)
    advance_days_min: int = Field(
        1, ge=0, description="开始日期最早是今天之后第几天（业务时区自然日，0 表示当天，且须晚于现在）"
    )
    advance_days_max: int = Field(30, ge=1, description="开始日期最晚是今天之后第几天（业务时区自然日）")

    @model_validator(mode="after")
    def valid_advance_window(self):
        if self.advance_days_max < self.advance_days_min:
            raise ValueError("advance_days_max 不能小于 advance_days_min")
        return self
