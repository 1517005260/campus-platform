"""消息消费：重复投递只处理一次。"""

import pytest
from app.consumers import handle_audit, handle_notification
from app.models import AuditLog, Notification
from campus_common.events import AuditRecord, Envelope, NotificationSend
from sqlalchemy import func, select

pytestmark = pytest.mark.db


def envelope(payload) -> Envelope:
    return Envelope(type=payload.TYPE, producer="m1-seat", payload=payload.model_dump(mode="json"))


async def test_duplicate_notification_processed_once(db):
    e = envelope(NotificationSend(user_ids=[1, 2], template="seat.remind_before"))
    await handle_notification(e)
    await handle_notification(e)
    assert db.scalar(select(func.count()).select_from(Notification)) == 2


async def test_audit_keeps_request_id(db):
    e = envelope(
        AuditRecord(
            actor_type="service",
            actor_id="m3-repair",
            module="m1",
            action="block.create",
            target_type="room",
            target_id="3",
        )
    )
    e.request_id = "req-1"
    await handle_audit(e)
    log = db.scalar(select(AuditLog))
    assert (log.request_id, log.actor_id) == ("req-1", "m3-repair")
