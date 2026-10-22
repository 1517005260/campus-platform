"""跨模块接口：按 ID 或按权限查用户。通知与审计的写入走消息，不提供 HTTP 写接口。"""

from typing import Annotated

from campus_common.auth import require_service
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES, not_found
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import schemas as s
from app.models import Permission, Role, User

router = APIRouter(prefix="/internal/v1", tags=["internal"], responses=ERROR_RESPONSES)

Caller = Annotated[str, Depends(require_service("m2-room", "m3-repair"))]


@router.get("/users/{user_id}", summary="查询用户（含邮箱）", response_model=s.UserContact)
async def get_user(user_id: int, caller: Caller, session: SessionDep):
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("用户", user_id)
    return s.UserContact.model_validate(user, from_attributes=True)


@router.get("/users", summary="按权限码（和院系）查用户", response_model=list[s.UserBrief])
async def users_with_perm(caller: Caller, session: SessionDep, perm: str, dept_id: int | None = None):
    """例如查本院系审批人：perm=room:approve&dept_id=3；查维修工：perm=repair:work。"""
    stmt = (
        select(User)
        .join(User.roles)
        .join(Role.perms)
        .where(Permission.code == perm, User.active.is_(True))
        .distinct()
        .order_by(User.id)
    )
    if dept_id is not None:
        stmt = stmt.where(User.dept_id == dept_id)
    users = (await session.scalars(stmt)).all()
    return [s.UserBrief.model_validate(u, from_attributes=True) for u in users]
