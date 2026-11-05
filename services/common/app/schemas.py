"""common 接口契约。"""

from typing import Annotated, Any, Literal

from campus_common.auth import CurrentUser
from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

# 去掉首尾空白后不能为空
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100, pattern=r"^[^@\s]+@[^@\s]+$")]
Password = Annotated[str, Field(min_length=8, max_length=72, description="bcrypt 只取前 72 字节")]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="秒")
    user: CurrentUser


# ---------------- 用户 ----------------


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None


class UserContact(UserBrief):
    email: str | None


class UserAdmin(UserBrief):
    email: str | None
    active: bool
    roles: list[str]
    created_at: AwareDatetime


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{2,50}$", description="字母、数字、_ . -，2–50 位")
    name: Name
    email: Email | None = None
    dept_id: int | None = None
    password: Password
    role_codes: list[str] = []


class UserUpdate(BaseModel):
    """只修改传入的字段；dept_id、email 传 null 表示清空（name 为 null 视为不修改）。
    active=false 停用（不能登录），true 恢复。"""

    name: Name | None = None
    email: Email | None = None
    dept_id: int | None = None
    active: bool | None = None
    password: Password | None = Field(None, description="重置密码")


class UserRolesUpdate(BaseModel):
    role_codes: list[str]


# ---------------- 角色与权限 ----------------


class RoleOut(BaseModel):
    code: str
    name: str
    builtin: bool
    perms: list[str]
    user_count: int = Field(0, description="拥有该角色的用户数（含停用用户）")


class RoleCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    name: Name
    perms: list[str]


class RoleUpdate(BaseModel):
    name: Name | None = None
    perms: list[str] | None = None


class PermissionOut(BaseModel):
    code: str
    module: str
    description: str


# ---------------- 院系 ----------------


class DeptOut(BaseModel):
    id: int
    name: str


class DeptIn(BaseModel):
    name: Name


# ---------------- 通知与审计 ----------------


class NotificationOut(BaseModel):
    id: int
    template: str
    title: str
    content: str
    ref: dict[str, Any] | None
    read_at: AwareDatetime | None
    created_at: AwareDatetime


class UnreadCount(BaseModel):
    count: int


class AuditLogOut(BaseModel):
    id: int
    at: AwareDatetime
    actor_type: str
    actor_id: str
    module: str
    action: str
    target_type: str
    target_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None
