"""工单状态机：上报到验收、下架与升级。"""

from datetime import timedelta

import pytest
from app import clients
from app.config import settings
from app.jobs import escalate_overdue
from app.models import Outbox, WorkOrder, WorkOrderEvent
from campus_common.errors import AppError
from campus_common.testing import record_service_calls, user_headers
from campus_common.timeutil import now
from sqlalchemy import select

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("db")]

WORKER_ID = 9001


def reporter():
    return user_headers(settings, perms=["repair:report"])


def dispatcher():
    return user_headers(settings, perms=["repair:dispatch"], user_id=2001)


def worker():
    return user_headers(settings, perms=["repair:work"], user_id=WORKER_ID)


def manager():
    return user_headers(settings, perms=["repair:manage"], user_id=4001)


def report(client, **extra):
    body = {"room_id": 3, "category": "空调", "description": "不制冷"}
    body.update(extra)
    response = client.post("/api/v1/repair/orders", json=body, headers=reporter())
    assert response.status_code == 201, response.text
    return response.json()


def dispatch(client, order_id, *, blocks_room=True):
    response = client.post(
        f"/api/v1/repair/orders/{order_id}/dispatch",
        json={
            "assignee_id": WORKER_ID,
            "deadline_at": (now() + timedelta(days=1)).isoformat(),
            "blocks_room": blocks_room,
        },
        headers=dispatcher(),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_flow_blocks_then_releases(client, db, monkeypatch):
    created = report(client)
    dispatched = dispatch(client, created["id"], blocks_room=True)
    assert dispatched["status"] == "dispatched"
    assert dispatched["blocks_room"] is True

    calls = record_service_calls(
        monkeypatch,
        clients.m1,
        {
            "block_id": 1,
            "cancelled_reservations": [],
            "released": True,
        },
    )
    started = client.post(f"/api/v1/repair/orders/{created['id']}/start", headers=worker())
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    assert calls[-1][0:2] == ("POST", "/internal/v1/blocks")
    assert calls[-1][2]["json"]["source"] == "M3_MAINTENANCE"
    assert calls[-1][2]["idempotency_key"] == f"m3-order-{created['id']}-block"

    completed = client.post(
        f"/api/v1/repair/orders/{created['id']}/complete",
        json={"note": "已更换"},
        headers=worker(),
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "pending_acceptance"
    assert [item[0] for item in calls] == ["POST"]

    rejected = client.post(
        f"/api/v1/repair/orders/{created['id']}/reject-acceptance",
        json={"reason": "仍不制冷"},
        headers=reporter(),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "in_progress"
    assert [item[0] for item in calls] == ["POST"]

    again = client.post(
        f"/api/v1/repair/orders/{created['id']}/complete",
        json={"note": "再次更换"},
        headers=worker(),
    )
    assert again.status_code == 200, again.text

    accepted = client.post(
        f"/api/v1/repair/orders/{created['id']}/accept",
        json={"rating": 5, "comment": "好了"},
        headers=reporter(),
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "closed"
    assert body["rating"] == 5
    assert calls[-1][0:2] == ("DELETE", f"/internal/v1/blocks/M3_MAINTENANCE/{created['id']}")

    db.expire_all()
    types = set(db.scalars(select(Outbox.type)).all())
    assert "notification.send" in types
    assert "m3.workorder.status_changed" in types


def test_m1_failure_does_not_start(client, db, monkeypatch):
    created = report(client)
    dispatch(client, created["id"], blocks_room=True)

    async def fail(*_args, **_kwargs):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr("app.orders.clients.block_room", fail)
    started = client.post(f"/api/v1/repair/orders/{created['id']}/start", headers=worker())
    assert started.status_code == 502
    assert started.json()["code"] == "UPSTREAM_UNAVAILABLE"

    db.expire_all()
    status = db.scalar(select(WorkOrder.status).where(WorkOrder.id == created["id"]))
    assert status == "dispatched"


def test_unknown_category_and_cancel_rules(client):
    bad = client.post(
        "/api/v1/repair/orders",
        json={"room_id": 3, "category": "电梯", "description": "停了"},
        headers=reporter(),
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "UNKNOWN_CATEGORY"

    created = report(client)
    other = client.post(
        f"/api/v1/repair/orders/{created['id']}/cancel",
        json={"reason": "不修了"},
        headers=user_headers(settings, perms=["repair:report"], user_id=1002),
    )
    assert other.status_code == 404

    cancelled = client.post(
        f"/api/v1/repair/orders/{created['id']}/cancel",
        json={"reason": "不修了"},
        headers=reporter(),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    again = client.post(
        f"/api/v1/repair/orders/{created['id']}/cancel",
        json={"reason": "再取消"},
        headers=reporter(),
    )
    assert again.status_code == 409
    assert again.json()["code"] == "ORDER_STATE_CONFLICT"


def test_worker_sees_only_assigned_orders_and_admin_accept_waits(client):
    first = report(client)
    second = report(client)
    dispatch(client, first["id"], blocks_room=False)
    listed = client.get("/api/v1/repair/orders", headers=worker())
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [first["id"]]

    client.post(f"/api/v1/repair/orders/{first['id']}/start", headers=worker())
    client.post(
        f"/api/v1/repair/orders/{first['id']}/complete",
        json={"note": "完成"},
        headers=worker(),
    )
    early = client.post(
        f"/api/v1/repair/orders/{first['id']}/accept",
        json={"rating": 4},
        headers=manager(),
    )
    assert early.status_code == 403
    assert early.json()["code"] == "ADMIN_ACCEPT_TOO_EARLY"
    assert client.get(f"/api/v1/repair/orders/{second['id']}", headers=worker()).status_code == 404


def test_not_assignee_cannot_start(client):
    created = report(client)
    dispatch(client, created["id"], blocks_room=False)
    started = client.post(
        f"/api/v1/repair/orders/{created['id']}/start",
        headers=user_headers(settings, perms=["repair:work"], user_id=3002),
    )
    assert started.status_code == 403
    assert started.json()["code"] == "NOT_ASSIGNEE"


def test_escalation_once_per_window(client, db):
    created = report(client)
    dispatch(client, created["id"], blocks_room=False)
    db.expire_all()
    event = db.scalar(
        select(WorkOrderEvent).where(
            WorkOrderEvent.order_id == created["id"], WorkOrderEvent.action == "dispatch"
        )
    )
    event.at = now() - timedelta(hours=25)
    db.commit()

    assert escalate_overdue(db, now()) == [created["id"]]
    db.commit()
    db.expire_all()
    level = db.scalar(select(WorkOrder.escalation_level).where(WorkOrder.id == created["id"]))
    assert level == 1
    assert escalate_overdue(db, now()) == []
