"""Inbox：消费端去重。

    async with sessions() as session, session.begin():
        if not await claim_message(session, Inbox, envelope):
            return            # 处理过了，直接 ack
        ...业务处理...        # 与 inbox 记录同一事务提交

业务失败时事务回滚，inbox 记录也随之撤销，消息重投后会被再次处理。
"""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from campus_common.events import Envelope

# 去重记录的保留期必须长于一条消息可能被重复投递的时间窗口（延迟重试最长约 4 小时，
# 加上死信重放），30 天足够覆盖
INBOX_RETENTION = timedelta(days=30)


async def claim_message(session: AsyncSession, inbox_model, envelope: Envelope) -> bool:
    """在当前事务中登记消息。首次处理返回 True，重复消息返回 False。"""
    result = await session.execute(
        insert(inbox_model)
        .values(message_id=envelope.message_id, type=envelope.type)
        .on_conflict_do_nothing()
        .returning(inbox_model.message_id)
    )
    return result.first() is not None


def purge_processed(
    session: Session, inbox_model, at: datetime, retention: timedelta = INBOX_RETENTION
) -> int:
    """删除早于保留期的去重记录，返回删除条数。由消费方服务的定时任务调用。"""
    result = session.execute(delete(inbox_model).where(inbox_model.processed_at < at - retention))
    return result.rowcount or 0
