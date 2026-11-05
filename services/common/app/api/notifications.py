"""我的站内通知。写入走消息（notification.send），见 app/consumers.py。"""

from campus_common.auth import CurrentUserDep
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends, Query

from app import notification_service as svc
from app import schemas as s

router = APIRouter(prefix="/api/v1/notifications", tags=["通知与审计"], responses=ERROR_RESPONSES)


@router.get("", summary="我的站内通知", response_model=Page[s.NotificationOut])
async def my_notifications(
    user: CurrentUserDep,
    session: SessionDep,
    unread: bool | None = Query(None, description="true 只看未读，false 只看已读"),
    p: PageParams = Depends(page_params),
):
    """只返回当前用户的通知，最新的在前。"""
    return await svc.list_mine(session, user.id, p, unread)


@router.get("/unread-count", summary="我的未读通知数", response_model=s.UnreadCount)
async def my_unread_count(user: CurrentUserDep, session: SessionDep):
    return s.UnreadCount(count=await svc.unread_count(session, user.id))


@router.post("/{notification_id}/read", summary="标为已读", status_code=204)
async def mark_read(notification_id: int, user: CurrentUserDep, session: SessionDep) -> None:
    """重复标记不报错，保留第一次的已读时间。错误：404 `NOT_FOUND`（不存在或不是自己的通知）。"""
    await svc.mark_read(session, user.id, notification_id)


@router.post("/read-all", summary="全部标为已读", status_code=204)
async def mark_all_read(user: CurrentUserDep, session: SessionDep) -> None:
    await svc.mark_all_read(session, user.id)
