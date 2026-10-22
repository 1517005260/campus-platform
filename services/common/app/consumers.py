"""跨模块消息消费者（FastStream）。启动：uvicorn app.consumers:app --port 8090（/health 供健康检查）

本文件只写业务处理函数；拓扑、重试与死信由公共库统一处理（campus_common.topology / consuming）：
- 每条消息先在 inbox 登记 message_id，与业务写入同一事务，重复投递只处理一次
- 永久错误（消息不合法、违反约束）直接进死信队列 campus.dlq.<队列名>
- 临时错误（数据库/网络不可用）进程内快速重试后转入延迟重试队列，依赖恢复后自动继续处理
- 业务需要明确分类时抛 campus_common.retry.PermanentError / TransientError
"""

from campus_common.consuming import create_broker, create_consumer_app, subscribe
from campus_common.db import make_async_sessionmaker
from campus_common.events import AuditRecord, Envelope, NotificationSend
from campus_common.inbox import claim_message
from campus_common.topology import AUDIT_QUEUE, NOTIFICATION_QUEUE

from app.config import settings
from app.models import AuditLog, Inbox, Notification

broker = create_broker(settings.rabbitmq_url)
sessions = make_async_sessionmaker(settings.database_url)


async def handle_notification(envelope: Envelope) -> None:
    payload = NotificationSend.model_validate(envelope.payload)
    async with sessions() as session, session.begin():
        if not await claim_message(session, Inbox, envelope):
            return
        for user_id in payload.user_ids:
            # 模板渲染由通知模块实现：template + params → title/content
            session.add(
                Notification(
                    user_id=user_id,
                    template=payload.template,
                    title=payload.template,
                    content=str(payload.params),
                    ref=payload.ref.model_dump() if payload.ref else None,
                    channels=payload.channels,
                )
            )


# 邮件由 worker 的 send_pending_emails 扫描发送，消费者只负责落库


async def handle_audit(envelope: Envelope) -> None:
    payload = AuditRecord.model_validate(envelope.payload)
    async with sessions() as session, session.begin():
        if not await claim_message(session, Inbox, envelope):
            return
        session.add(
            AuditLog(
                at=envelope.occurred_at,
                request_id=envelope.request_id,
                message_id=str(envelope.message_id),
                **payload.model_dump(),
            )
        )


subscribe(broker, NOTIFICATION_QUEUE, handle_notification)
subscribe(broker, AUDIT_QUEUE, handle_audit)

app = create_consumer_app(broker, settings.rabbitmq_url, (NOTIFICATION_QUEUE, AUDIT_QUEUE))
