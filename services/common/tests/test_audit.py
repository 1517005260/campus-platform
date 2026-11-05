"""审计查询（REQ-D-08）：按操作人、模块、动作、对象、时间筛选，最新在前，需要 audit:read。"""

from datetime import UTC, datetime, timedelta

import pytest
from app.models import AuditLog
from campus_common.timeutil import BIZ_TZ
from sqlalchemy import delete

from tests.conftest import headers_for

pytestmark = pytest.mark.db

AUDITOR = headers_for(39, ["audit:read"])
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=BIZ_TZ)


@pytest.fixture
def logs(db):
    db.execute(delete(AuditLog))
    rows = [
        # actor_id, module, action, target_type, target_id, 相对 T0 的分钟
        ("11", "common", "user.create", "user", "12", 0),
        ("m2-room", "m1", "block.create", "room_block", "1", 30),
        ("m3-repair", "m1", "block.create", "room_block", "2", 60),
        ("m3-repair", "m1", "block.release", "room_block", "2", 90),
    ]
    for actor, module, action, ttype, tid, minutes in rows:
        db.add(
            AuditLog(
                at=T0 + timedelta(minutes=minutes),
                actor_type="service" if "-" in actor else "user",
                actor_id=actor,
                module=module,
                action=action,
                target_type=ttype,
                target_id=tid,
                request_id=f"req-{minutes}",
            )
        )
    db.commit()


def query(client, **params):
    resp = client.get("/api/v1/audit", params=params, headers=AUDITOR)
    assert resp.status_code == 200, resp.json()
    return [(r["actor_id"], r["action"], r["target_id"]) for r in resp.json()["items"]]


def test_filters_by_actor_module_and_target(client, logs):
    assert query(client, actor_id="m3-repair") == [
        ("m3-repair", "block.release", "2"),
        ("m3-repair", "block.create", "2"),
    ]
    assert query(client, module="common") == [("11", "user.create", "12")]
    assert query(client, target_type="room_block", target_id="1") == [("m2-room", "block.create", "1")]
    assert query(client, module="m1", action="block.create") == [
        ("m3-repair", "block.create", "2"),
        ("m2-room", "block.create", "1"),
    ]


def test_time_range_includes_start_excludes_end(client, logs):
    window = {
        "date_from": (T0 + timedelta(minutes=30)).isoformat(),
        "date_to": (T0 + timedelta(minutes=90)).isoformat(),
    }
    assert [a for _, a, _ in query(client, **window)] == ["block.create", "block.create"]
    # 同一时刻用 UTC 表示，结果相同
    utc = {k: datetime.fromisoformat(v).astimezone(UTC).isoformat() for k, v in window.items()}
    assert utc["date_from"].endswith("+00:00")
    assert len(query(client, **utc)) == 2


def test_naive_time_rejected(client, logs):
    resp = client.get("/api/v1/audit", params={"date_from": "2026-11-05T09:00:00"}, headers=AUDITOR)
    assert (resp.status_code, resp.json()["code"]) == (422, "VALIDATION_ERROR")


def test_paginated_newest_first_in_business_timezone(client, logs):
    page = client.get("/api/v1/audit?size=3", headers=AUDITOR).json()
    assert page["total"] == 4 and len(page["items"]) == 3
    assert page["items"][0]["at"] == "2026-11-05T10:30:00+08:00"
    assert page["items"][0]["request_id"] == "req-90"


def test_requires_audit_read(client, logs):
    resp = client.get("/api/v1/audit", headers=headers_for(1, ["seat:reserve", "admin:user"]))
    assert (resp.status_code, resp.json()["code"]) == (403, "FORBIDDEN")
