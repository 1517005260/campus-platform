"""消息消费：模板渲染、重复投递只处理一次、审计保留 request_id。"""

import pytest
from app.consumers import handle_audit, handle_notification
from app.models import AuditLog, Notification
from app.seed import seed_base
from campus_common.events import AuditRecord, Envelope, NotificationSend
from sqlalchemy import func, select

pytestmark = pytest.mark.db


@pytest.fixture
def db_seed():
    return seed_base  # 不含演示通知与审计


def envelope(payload) -> Envelope:
    return Envelope(type=payload.TYPE, producer="m1-seat", payload=payload.model_dump(mode="json"))


SLOT = {"reservation_id": 7, "start_at": "2026-11-05T06:00:00+00:00", "end_at": "2026-11-05T08:00:00+00:00"}


async def test_duplicate_notification_processed_once(db):
    e = envelope(NotificationSend(user_ids=[1, 2], template="seat.remind_before", params=SLOT))
    await handle_notification(e)
    await handle_notification(e)
    assert db.scalar(select(func.count()).select_from(Notification)) == 2


async def test_notification_rendered_in_business_timezone(db):
    await handle_notification(
        envelope(
            NotificationSend(
                user_ids=[1],
                template="seat.reservation_cancelled_by_admin",
                params=SLOT | {"cause": "seat_disabled"},
            )
        )
    )
    n = db.scalar(select(Notification))
    assert n.title == "预约因座位停用被取消"
    assert "11月5日 14:00–16:00" in n.content  # UTC 06:00 = 北京时间 14:00
    assert n.channels == ["inapp", "email"] and n.email_sent_at is None


@pytest.mark.parametrize(
    ("cause", "title", "phrase"),
    [
        ("seat_disabled", "预约因座位停用被取消", "自习座位已被管理员停用"),
        ("room_disabled", "预约因自习室停用被取消", "所在的自习室已被管理员停用"),
        ("room_deregistered", "预约因自习室注销被取消", "已不再作为自习室开放"),
    ],
)
async def test_admin_cancellation_states_the_actual_cause(db, cause, title, phrase):
    await handle_notification(
        envelope(
            NotificationSend(
                user_ids=[1],
                template="seat.reservation_cancelled_by_admin",
                params=SLOT | {"cause": cause},
            )
        )
    )
    n = db.scalar(select(Notification))
    assert n.title == title
    assert phrase in n.content


async def test_block_cancellation_names_the_cause(db):
    params = SLOT | {"block_source": "M3_MAINTENANCE", "block_ref_id": 3, "reason": "空调维修"}
    await handle_notification(
        envelope(
            NotificationSend(user_ids=[1], template="seat.reservation_cancelled_by_block", params=params)
        )
    )
    assert "（维修：空调维修）" in db.scalar(select(Notification.content))


@pytest.mark.parametrize(
    ("template", "params"),
    [
        ("room.unknown_template", {"application_id": 3}),
        ("seat.remind_late", {"start_at": "2026-11-05T06:00:00+00:00"}),
    ],
)
async def test_unknown_template_or_missing_params_still_stored(db, template, params):
    await handle_notification(envelope(NotificationSend(user_ids=[1], template=template, params=params)))
    n = db.scalar(select(Notification))
    assert n.title == template and str(next(iter(params.values()))) in n.content


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
