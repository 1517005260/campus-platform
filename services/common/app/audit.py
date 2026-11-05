"""操作审计：写入与全平台审计查询。

其他服务的审计经 audit.record 消息写入（consumers.handle_audit 调用 record()）；common 的管理操作与业务数据
在同一事务里直接调用 record()，不经过消息。before/after 只放业务字段，不放密码哈希。
"""

from datetime import datetime
from typing import Any

from campus_common.context import request_id_var
from campus_common.pagination import Page, PageParams, paginate
from campus_common.timeutil import now
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas as s
from app.models import AuditLog


def record(
    session,
    actor_type: str,
    actor_id: int | str,
    action: str,
    target_type: str,
    target_id: int | str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    module: str = "common",
    at: datetime | None = None,
    request_id: str | None = None,
    message_id: str | None = None,
) -> None:
    """写一条审计。common 自身的操作用默认值（模块 common、当前时刻、当前请求的 request_id）；
    消费 audit.record 消息时传入消息里的模块、发生时间、request_id 与 message_id。
    只修改会话，由调用方提交；同步、异步会话都可用。"""
    session.add(
        AuditLog(
            at=at or now(),
            actor_type=actor_type,
            actor_id=str(actor_id),
            module=module,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            before=before,
            after=after,
            request_id=request_id or request_id_var.get(),
            message_id=message_id,
        )
    )


async def query(
    session: AsyncSession,
    params: PageParams,
    *,
    actor_id: str | None = None,
    module: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Page[s.AuditLogOut]:
    """按条件精确匹配；时间为 [date_from, date_to)。最新的在前。"""
    stmt = select(AuditLog)
    for column, value in (
        (AuditLog.actor_id, actor_id),
        (AuditLog.module, module),
        (AuditLog.action, action),
        (AuditLog.target_type, target_type),
        (AuditLog.target_id, target_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if date_from is not None:
        stmt = stmt.where(AuditLog.at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.at < date_to)
    return await paginate(
        session,
        stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc()),
        params,
        lambda row: s.AuditLogOut.model_validate(row, from_attributes=True),
    )
