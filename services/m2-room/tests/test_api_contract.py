"""接口层行为：鉴权、参数校验、资格门槛、对 M1 的调用约定。"""

from datetime import datetime, timedelta

import pytest
from app import clients
from app.models import Setting
from app.seed import seed_base
from campus_common.testing import record_service_calls
from campus_common.timeutil import now
from sqlalchemy import update


def test_submit_requires_apply_permission(client, as_approver):
    resp = client.post(
        "/api/v1/room/applications",
        json={
            "room_id": 1,
            "start_at": "2026-10-20T14:00:00+08:00",
            "end_at": "2026-10-20T16:00:00+08:00",
            "purpose": "读书会",
            "attendees": 30,
        },
        headers=as_approver,
    )
    assert resp.status_code == 403


def test_submit_rejects_end_before_start(client, as_applicant):
    resp = client.post(
        "/api/v1/room/applications",
        json={
            "room_id": 1,
            "start_at": "2026-10-20T16:00:00+08:00",
            "end_at": "2026-10-20T14:00:00+08:00",
            "purpose": "读书会",
            "attendees": 30,
        },
        headers=as_applicant,
    )
    assert resp.status_code == 422


@pytest.fixture
def db_seed():
    return seed_base  # 申请参数默认值（违约上限 3 次、统计窗口 30 天）


def violation_lookup(monkeypatch, count: int):
    return record_service_calls(monkeypatch, clients.m1, {"user_id": 1001, "count": count})


@pytest.mark.db
def test_eligibility_blocks_at_violation_limit(client, db, as_applicant, monkeypatch):
    violation_lookup(monkeypatch, 3)
    body = client.get("/api/v1/room/eligibility", headers=as_applicant).json()
    assert body["eligible"] is False
    assert "3 次" in body["reasons"][0]


@pytest.mark.db
def test_eligibility_allows_below_limit_and_queries_window(client, db, as_applicant, monkeypatch):
    calls = violation_lookup(monkeypatch, 2)
    before = now()
    assert client.get("/api/v1/room/eligibility", headers=as_applicant).json()["eligible"] is True
    after = now()
    (method, path, kwargs) = calls[0]
    assert (method, path) == ("GET", "/internal/v1/users/1001/violations")
    since = datetime.fromisoformat(kwargs["params"]["since"])
    assert before - timedelta(days=30) <= since <= after - timedelta(days=30)


@pytest.mark.db
def test_eligibility_uses_adjusted_limit(client, db, as_applicant, monkeypatch):
    db.execute(update(Setting).where(Setting.key == "max_violations").values(value=2))
    db.commit()
    violation_lookup(monkeypatch, 2)
    assert client.get("/api/v1/room/eligibility", headers=as_applicant).json()["eligible"] is False


async def test_occupy_room_uses_stable_idempotency_key(monkeypatch):
    calls = record_service_calls(monkeypatch, clients.m1, {"block_id": 9, "cancelled_reservations": []})
    t = now()
    await clients.occupy_room(42, 1, t, t, "整教室预约")
    await clients.occupy_room(42, 1, t, t, "整教室预约")

    method, path, kwargs = calls[0]
    assert (method, path) == ("POST", "/internal/v1/blocks")
    assert kwargs["json"]["source"] == "M2_OCCUPY"
    assert kwargs["json"]["ref_id"] == 42
    assert {c[2]["idempotency_key"] for c in calls} == {"m2-app-42-occupy"}
