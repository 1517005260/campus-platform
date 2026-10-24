"""common 接口契约。"""

from typing import Any, Literal

from campus_common.auth import CurrentUser
from pydantic import AwareDatetime, BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="秒")
    user: CurrentUser


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


class UserCreate(BaseModel):
    username: str = Field(max_length=50)
    name: str = Field(max_length=50)
    email: str | None = None
    dept_id: int | None = None
    password: str = Field(min_length=8)
    role_codes: list[str] = []


class UserRolesUpdate(BaseModel):
    role_codes: list[str]


class RoleOut(BaseModel):
    code: str
    name: str
    builtin: bool
    perms: list[str]


class RoleCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    name: str = Field(max_length=50)
    perms: list[str]


class RoleUpdate(BaseModel):
    name: str | None = None
    perms: list[str] | None = None


class PermissionOut(BaseModel):
    code: str
    module: str
    description: str


class DeptOut(BaseModel):
    id: int
    name: str


class NotificationOut(BaseModel):
    id: int
    template: str
    title: str
    content: str
    ref: dict[str, Any] | None
    read_at: AwareDatetime | None
    created_at: AwareDatetime


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
