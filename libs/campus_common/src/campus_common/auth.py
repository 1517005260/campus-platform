"""鉴权。

用户：common 用 HS256 签发 JWT，各服务用同一个 JWT_SECRET 本地校验，不回调 common。
     权限判断一律按权限码（perms），不按角色名，因为管理员可以新建角色。
服务间：/internal/v1/* 只接受 X-Service-Name + X-Service-Key，不接受用户 token。
"""

import hmac
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from campus_common.errors import AppError
from campus_common.settings import ServiceSettings
from campus_common.timeutil import now

ALGORITHM = "HS256"


class CurrentUser(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None
    roles: list[str]
    perms: list[str]

    def has(self, perm: str) -> bool:
        return perm in self.perms


def create_token(user: CurrentUser, settings: ServiceSettings) -> str:
    issued = now()
    claims = {
        "sub": str(user.id),
        "username": user.username,
        "name": user.name,
        "dept_id": user.dept_id,
        "roles": user.roles,
        "perms": user.perms,
        "typ": "user",
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, settings: ServiceSettings) -> CurrentUser:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise AppError(401, "TOKEN_EXPIRED", "登录已过期，请重新登录") from e
    except jwt.InvalidTokenError as e:
        raise AppError(401, "TOKEN_INVALID", "无效的登录凭证") from e
    if claims.get("typ") != "user":
        raise AppError(401, "TOKEN_INVALID", "无效的登录凭证")
    try:
        return CurrentUser(
            id=int(claims["sub"]),
            username=claims["username"],
            name=claims["name"],
            dept_id=claims.get("dept_id"),
            roles=claims.get("roles", []),
            perms=claims.get("perms", []),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise AppError(401, "TOKEN_INVALID", "无效的登录凭证") from e


_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> ServiceSettings:
    return request.app.state.settings


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[ServiceSettings, Depends(get_settings)],
) -> CurrentUser:
    if creds is None:
        raise AppError(401, "UNAUTHENTICATED", "需要登录")
    return decode_token(creds.credentials, settings)


def require_perm(*perms: str):
    """要求当前用户拥有任一权限码。用法：user = Depends(require_perm("seat:reserve"))"""

    def dep(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not any(user.has(p) for p in perms):
            raise AppError(403, "FORBIDDEN", f"需要权限：{' 或 '.join(perms)}")
        return user

    return dep


def require_service(*allowed: str):
    """服务间接口鉴权，返回调用方服务名（写审计用）。"""

    def dep(
        settings: Annotated[ServiceSettings, Depends(get_settings)],
        x_service_name: Annotated[str | None, Header()] = None,
        x_service_key: Annotated[str | None, Header()] = None,
    ) -> str:
        expected = settings.service_keys.get(x_service_name or "")
        if expected is None or not hmac.compare_digest((x_service_key or "").encode(), expected.encode()):
            raise AppError(401, "SERVICE_UNAUTHENTICATED", "服务身份校验失败")
        if x_service_name not in allowed:
            raise AppError(403, "SERVICE_FORBIDDEN", f"{x_service_name} 无权调用该接口")
        return x_service_name

    return dep


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
