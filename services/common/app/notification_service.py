"""站内通知（REQ-D-05）：生成（渲染模板）、查询与已读。

其他服务的通知经消息写入（consumers.handle_notification），common 自身的通知（角色变更、演示数据的欢迎信）
也用 new_notification() 生成。用户只能看到和修改自己的通知。
"""

from typing import Any

from campus_common.errors import not_found
from campus_common.pagination import Page, PageParams, paginate
from campus_common.timeutil import now
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import Notification
from app.templates import render


def new_notification(
    user_id: int,
    template: str,
    params: dict[str, Any],
    *,
    channels: list[str],
    ref: dict[str, Any] | None = None,
) -> Notification:
    """按模板渲染标题与正文，返回待加入会话的通知（未知模板也会生成，见 templates.render）。"""
    title, content = render(template, params)
    return Notification(
        user_id=user_id,
        template=template,
        title=title[:100],
        content=content,
        ref=ref,
        channels=channels,
    )


def notification_out(n: Notification) -> s.NotificationOut:
    return s.NotificationOut.model_validate(n, from_attributes=True)


async def list_mine(
    session: AsyncSession, user_id: int, params: PageParams, unread: bool | None = None
) -> Page[s.NotificationOut]:
    """最新的在前；unread=true 只看未读，false 只看已读。"""
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread is not None:
        stmt = stmt.where(Notification.read_at.is_(None) if unread else Notification.read_at.is_not(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    return await paginate(session, stmt, params, notification_out)


async def unread_count(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    return await session.scalar(stmt) or 0


async def mark_read(session: AsyncSession, user_id: int, notification_id: int) -> None:
    """幂等：已读的通知保留第一次的已读时间。别人的通知与不存在的一样返回 404。"""
    async with session.begin():
        exists = await session.scalar(
            select(Notification.id).where(Notification.id == notification_id, Notification.user_id == user_id)
        )
        if exists is None:
            raise not_found("通知", notification_id)
        await session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.read_at.is_(None))
            .values(read_at=now())
        )


async def mark_all_read(session: AsyncSession, user_id: int) -> int:
    """把自己的全部未读通知标为已读，返回本次标记的条数。"""
    async with session.begin():
        result = await session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=now())
        )
    return result.rowcount
