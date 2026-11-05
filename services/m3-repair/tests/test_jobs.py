"""超时升级：边界两侧、每个周期升级一次、不依赖 common、不被大量未到期工单饿死。时刻作为参数注入。"""

from datetime import timedelta

import pytest
from app import jobs
from app.jobs import escalate_overdue
from app.models import Outbox, WorkOrder, WorkOrderEvent
from campus_common.testing import NOW
from sqlalchemy import select

from tests.test_orders import act, dispatch, report

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("db")]

DAY = timedelta(hours=24)  # 默认规则：dispatched 超过 24 小时升级


def run(db, at):
    with db.begin():
        return escalate_overdue(db, at)


def escalations(db, order_id) -> list[dict]:
    db.expire_all()
    rows = db.scalars(select(Outbox).where(Outbox.type == "notification.send")).all()
    return [
        row.envelope["payload"]
        for row in rows
        if row.envelope["payload"]["template"] == "repair.escalated"
        and row.envelope["payload"]["params"]["order_id"] == order_id
    ]


@pytest.fixture
def dispatched(client, db, as_reporter, as_dispatcher, common_calls):
    order_id = report(client, as_reporter)
    assert dispatch(client, as_dispatcher, order_id).status_code == 200
    db.commit()
    return order_id


def test_escalates_exactly_at_timeout_and_once_per_period(db, dispatched):
    assert run(db, NOW + DAY - timedelta(seconds=1)) == []
    assert run(db, NOW + DAY) == [dispatched]
    assert run(db, NOW + DAY) == []  # 重复执行不重复升级
    assert run(db, NOW + 2 * DAY - timedelta(seconds=1)) == []
    assert run(db, NOW + 2 * DAY) == [dispatched]

    db.expire_all()
    order = db.get(WorkOrder, dispatched)
    assert (order.status, order.escalation_level) == ("dispatched", 2)
    events = db.scalars(
        select(WorkOrderEvent).where(
            WorkOrderEvent.order_id == dispatched, WorkOrderEvent.action == "escalate"
        )
    ).all()
    assert [(e.at, e.actor_id, e.from_status, e.to_status) for e in events] == [
        (NOW + DAY, None, "dispatched", "dispatched"),
        (NOW + 2 * DAY, None, "dispatched", "dispatched"),
    ]


def test_escalation_notifies_manage_permission_holders(db, dispatched):
    run(db, NOW + DAY)
    run(db, NOW + 2 * DAY)
    first, second = escalations(db, dispatched)
    assert (first["user_ids"], first["perm"]) == ([], "repair:manage")
    assert first["params"] == {
        "order_id": dispatched,
        "category": "空调",
        "status": "dispatched",
        "since": NOW.isoformat(),
        "timeout_hours": 24,
        "level": 1,
    }
    assert second["params"]["level"] == 2


def test_escalation_does_not_call_common(db, dispatched, common_calls):
    calls_before = len(common_calls)
    assert run(db, NOW + DAY) == [dispatched]
    assert len(common_calls) == calls_before


def test_status_change_restarts_the_clock(client, db, dispatched, as_worker, clock):
    clock.shift(timedelta(hours=1))
    assert act(client, as_worker, dispatched, "start").status_code == 200  # in_progress 规则：72 小时
    started = NOW + timedelta(hours=1)
    assert run(db, NOW + DAY) == []  # 已离开 dispatched，不再按派单时间计时
    assert run(db, started + timedelta(hours=72) - timedelta(seconds=1)) == []
    assert run(db, started + timedelta(hours=72)) == [dispatched]


def test_overdue_order_found_behind_a_full_batch_of_not_due_orders(
    client, db, as_reporter, as_dispatcher, common_calls, clock, monkeypatch
):
    monkeypatch.setattr(jobs, "BATCH", 5)
    not_due = [report(client, as_reporter) for _ in range(jobs.BATCH + 1)]
    overdue = report(client, as_reporter)
    dispatch(client, as_dispatcher, overdue)
    clock.shift(timedelta(hours=1))
    for order_id in not_due:
        dispatch(client, as_dispatcher, order_id)

    assert run(db, NOW + DAY) == [overdue]
