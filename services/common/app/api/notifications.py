"""站内通知与审计查询。写入走消息（notification.send / audit.record），见 app/consumers.py。"""

from datetime import datetime

from campus_common.auth import CurrentUserDep, require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from fastapi import APIRouter, Depends

from app import schemas as s

router = APIRouter(prefix="/api/v1", tags=["通知与审计"], responses=ERROR_RESPONSES)


@router.get("/notifications", summary="我的站内通知", response_model=Page[s.NotificationOut])
async def my_notifications(
    user: CurrentUserDep, unread: bool | None = None, p: PageParams = Depends(page_params)
):
    return page_of([], 0, p)


@router.post("/notifications/{notification_id}/read", summary="标为已读", status_code=204)
async def mark_read(notification_id: int, user: CurrentUserDep) -> None:
    return None


@router.get("/audit", summary="查询操作审计", response_model=Page[s.AuditLogOut])
async def query_audit(
    actor_id: str | None = None,
    module: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    p: PageParams = Depends(page_params),
    user=Depends(require_perm("audit:read")),
):
    return page_of([], 0, p)
