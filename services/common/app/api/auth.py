"""登录与当前用户。"""

from campus_common.auth import CurrentUser, CurrentUserDep, create_token, get_settings
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES, AppError
from campus_common.settings import ServiceSettings
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import schemas as s
from app.models import User
from app.security import verify_password_async

router = APIRouter(prefix="/api/v1/auth", tags=["鉴权"], responses=ERROR_RESPONSES)


def to_current_user(user: User) -> CurrentUser:
    perms = sorted({p.code for role in user.roles for p in role.perms})
    return CurrentUser(
        id=user.id,
        username=user.username,
        name=user.name,
        dept_id=user.dept_id,
        roles=[r.code for r in user.roles],
        perms=perms,
    )


@router.post("/login", summary="用户名密码登录，签发 JWT", response_model=s.LoginResponse)
async def login(
    body: s.LoginRequest,
    session: SessionDep,
    settings: ServiceSettings = Depends(get_settings),
):
    user = await session.scalar(select(User).where(User.username == body.username))
    password_ok = await verify_password_async(body.password, user.password_hash if user else None)
    if user is None or not user.active or not password_ok:
        raise AppError(401, "LOGIN_FAILED", "用户名或密码错误")
    current = to_current_user(user)
    return s.LoginResponse(
        access_token=create_token(current, settings),
        expires_in=settings.jwt_ttl_minutes * 60,
        user=current,
    )


@router.get("/me", summary="当前登录用户（来自 token）", response_model=CurrentUser)
async def me(user: CurrentUserDep):
    return user
