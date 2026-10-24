"""Outbox：保证"业务成功则消息一定发出"。

1. 业务代码调用 add_event()，消息与业务数据在同一个事务里写入本服务的 outbox 表。
2. Beat 每 2 秒触发 relay_outbox()，用 SKIP LOCKED 抢行后发布到 RabbitMQ，
   broker 确认后才标记 published_at。多个 worker 同时投递也不会重复抢到同一行。
3. 单条消息自身的错误（无法序列化等）只跳过这一条，attempts 递增并排到队尾，不阻塞其他消息；
   其他错误（broker 不可用、账号无权限等对每条消息都一样的错误）停止本批，下一轮重试。
4. 已发布超过保留期的行定期清理，表保持在"最近几天"的规模。

消息至少投递一次，消费端用 inbox 去重。
"""

import logging
import time
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from campus_common.context import request_id_var
from campus_common.events import Envelope
from campus_common.publisher import EventPublisher, is_message_error
from campus_common.timeutil import now

log = logging.getLogger(__name__)

OUTBOX_RETENTION = timedelta(days=7)
PURGE_INTERVAL_SECONDS = 600
_last_purge: dict[str, float] = {}


def add_event(session, outbox_model, producer: str, payload: BaseModel) -> Envelope:
    """把一条消息加入当前事务。session 可以是同步或异步会话，调用方负责 commit。"""
    envelope = Envelope(
        type=payload.TYPE,  # type: ignore[attr-defined]
        producer=producer,
        request_id=request_id_var.get(),
        payload=payload.model_dump(mode="json"),
    )
    session.add(
        outbox_model(
            id=envelope.message_id,
            type=envelope.type,
            envelope=envelope.model_dump(mode="json"),
            attempts=0,
        )
    )
    return envelope


def relay_outbox(
    sessions: sessionmaker[Session], outbox_model, publisher: EventPublisher, batch: int = 100
) -> int:
    """投递一批未发布的消息，返回成功条数。"""
    sent = 0
    with sessions() as session, session.begin():
        rows = session.scalars(
            select(outbox_model)
            .where(outbox_model.published_at.is_(None))
            .order_by(outbox_model.attempts, outbox_model.created_at)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.attempts += 1
            try:
                publisher.publish(row.envelope, routing_key=row.type)
            except Exception as exc:
                if is_message_error(exc):
                    log.exception("消息 %s 投递失败（第 %s 次），跳过", row.id, row.attempts)
                    continue
                log.warning("投递出错，本批停止：%s: %s", type(exc).__name__, exc)
                break
            row.published_at = now()
            sent += 1
    _purge_if_due(sessions, outbox_model)
    return sent


def purge_published(
    session: Session, outbox_model, at: datetime, retention: timedelta = OUTBOX_RETENTION
) -> int:
    """删除发布时间早于保留期的行，返回删除条数。"""
    result = session.execute(delete(outbox_model).where(outbox_model.published_at < at - retention))
    return result.rowcount or 0


def _purge_if_due(sessions: sessionmaker[Session], outbox_model) -> None:
    key = outbox_model.__table__.fullname
    if time.monotonic() - _last_purge.get(key, float("-inf")) < PURGE_INTERVAL_SECONDS:
        return
    _last_purge[key] = time.monotonic()
    with sessions() as session, session.begin():
        removed = purge_published(session, outbox_model, now())
    if removed:
        log.info("清理 %s 中 %s 条已发布消息", key, removed)
