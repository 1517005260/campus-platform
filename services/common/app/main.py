from campus_common.app_factory import create_app

from app.api import admin, auth, internal, notifications
from app.config import settings

app = create_app(
    settings,
    title="common 公共服务",
    description="登录与 JWT 签发、RBAC（用户/角色/权限/院系）、站内通知与邮件、操作审计。",
    routers=[auth.router, admin.router, notifications.router, internal.router],
)
