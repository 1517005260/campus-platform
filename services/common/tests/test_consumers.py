"""消息消费：模板渲染、重复投递只处理一次、审计保留 request_id。"""

import pytest
from app.consumers import handle_audit, handle_notification
from app.models import AuditLog, Dept, Notification, Role, User
from app.seed import BOOTSTRAP_ADMIN, seed_base
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


def _user(db, user_id: int, role: str, *, active: bool = True, dept_id: int | None = None) -> None:
    db.add(
        User(
            id=user_id,
            username=f"u{user_id}",
            password_hash="x",
            name=f"用户{user_id}",
            active=active,
            dept_id=dept_id,
            roles=[db.get(Role, role)],
        )
    )
    db.commit()


async def test_perm_addressed_notification_reaches_active_holders_once(db):
    _user(db, 50, "repair_dispatcher")
    _user(db, 51, "repair_dispatcher", active=False)
    _user(db, 52, "repair_worker")
    payload = NotificationSend(
        user_ids=[52, 50],
        perm="repair:manage",
        template="repair.escalated",
        params=ESCALATED,
    )
    await handle_notification(envelope(payload))
    # repair:manage：调度员 50 与系统管理员；停用的 51 不收；50 同时在 user_ids 中也只收一条
    recipients = db.scalars(select(Notification.user_id).order_by(Notification.user_id)).all()
    assert recipients == sorted([50, 52, BOOTSTRAP_ADMIN.id])


async def test_perm_addressed_notification_with_dept_reaches_only_that_departments_holders(db):
    db.add_all([Dept(id=1, name="院系一"), Dept(id=2, name="院系二")])
    _user(db, 60, "dept_approver", dept_id=1)
    _user(db, 61, "dept_approver", dept_id=2)
    _user(db, 62, "dept_approver", dept_id=1, active=False)
    _user(db, 63, "student", dept_id=1)
    payload = NotificationSend(user_ids=[63], perm="room:approve", dept_id=1, template="x", params={})
    await handle_notification(envelope(payload))
    # 院系 1 的启用审批人 60；院系 2 的 61 与无院系的系统管理员不收；user_ids 照常送达
    assert db.scalars(select(Notification.user_id).order_by(Notification.user_id)).all() == [60, 63]


async def test_dept_without_perm_only_reaches_listed_users(db):
    db.add(Dept(id=1, name="院系一"))
    _user(db, 60, "dept_approver", dept_id=1)
    await handle_notification(envelope(NotificationSend(user_ids=[1], dept_id=1, template="x", params={})))
    assert db.scalars(select(Notification.user_id)).all() == [1]


ORDER = {"order_id": 7, "category": "空调"}
ESCALATED = ORDER | {
    "status": "in_progress",
    "since": "2026-11-05T06:00:00+00:00",
    "timeout_hours": 72,
    "level": 2,
}


@pytest.mark.parametrize(
    ("template", "params", "title", "content"),
    [
        (
            "repair.reported",
            ORDER | {"room": "第三教学楼 H3106"},
            "新的报修待派单",
            "第三教学楼 H3106 报修了空调故障（报修工单 #7），请尽快派单。",
        ),
        (
            "repair.cancelled",
            ORDER | {"reason": "已自行修好"},
            "报修工单已取消",
            "报修工单 #7（空调）已被报修人取消，无需派单。取消原因：已自行修好",
        ),
        (
            "repair.dispatched",
            ORDER | {"deadline_at": "2026-11-05T10:00:00+00:00", "blocks_room": True},
            "你有新的维修任务",
            "报修工单 #7（空调）已派给你，请在 11月5日 18:00 前完成。"
            "开始维修时系统会下架整间教室，验收通过后恢复。",
        ),
        (
            "repair.dispatched",
            ORDER | {"deadline_at": "2026-11-05T10:00:00+00:00", "blocks_room": False},
            "你有新的维修任务",
            "报修工单 #7（空调）已派给你，请在 11月5日 18:00 前完成。",
        ),
        (
            "repair.started",
            ORDER | {"blocks_room": True},
            "报修工单开始维修",
            "你提交的报修工单 #7（空调）已开始维修，维修期间该教室暂停预约。",
        ),
        (
            "repair.completed",
            ORDER | {"note": "已更换压缩机", "accept_after_hours": 72},
            "报修工单待验收",
            "你提交的报修工单 #7（空调）已完工：已更换压缩机。"
            "请确认后验收评价；完工 72 小时后仍未验收的，管理员可代为验收。",
        ),
        (
            "repair.rejected",
            ORDER | {"reason": "仍不制冷", "blocks_room": False},
            "维修验收未通过",
            "报修工单 #7（空调）验收未通过：仍不制冷。请继续维修。",
        ),
        (
            "repair.accepted",
            ORDER | {"rating": 4, "by_admin": True},
            "维修工单已验收",
            "报修工单 #7（空调）已由管理员代为验收通过，评分 4 星。",
        ),
        (
            "repair.escalated",
            ESCALATED,
            "报修工单超时升级",
            "报修工单 #7（空调）自 11月5日 14:00 起处于“维修中”状态，"
            "每超过 72 小时升级一次，现已升级到第 2 级，请督办。",
        ),
    ],
)
async def test_repair_templates_describe_the_event_in_business_time(db, template, params, title, content):
    await handle_notification(envelope(NotificationSend(user_ids=[1], template=template, params=params)))
    n = db.scalar(select(Notification))
    assert (n.title, n.content) == (title, content)


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
