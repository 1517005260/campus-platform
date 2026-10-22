"""接口层行为：鉴权、参数校验、对 M1 的调用约定。"""

from app import clients
from campus_common.testing import record_service_calls
from campus_common.timeutil import now


def test_report_requires_login(client):
    assert client.post("/api/v1/repair/orders", json={}).status_code == 401


def test_reporter_cannot_dispatch(client, as_reporter):
    resp = client.post(
        "/api/v1/repair/orders/1/dispatch",
        json={"assignee_id": 3001, "deadline_at": "2026-10-21T18:00:00+08:00"},
        headers=as_reporter,
    )
    assert resp.status_code == 403


def test_rating_must_be_1_to_5(client, as_reporter):
    resp = client.post("/api/v1/repair/orders/1/accept", json={"rating": 6}, headers=as_reporter)
    assert resp.status_code == 422


async def test_block_and_release_target_same_m1_record(monkeypatch):
    calls = record_service_calls(
        monkeypatch, clients.m1, {"block_id": 1, "cancelled_reservations": [], "released": True}
    )

    await clients.block_room(7, 3, now(), "维修中")
    await clients.release_room(7)

    (m1, p1, k1), (m2, p2, _) = calls
    assert (m1, p1) == ("POST", "/internal/v1/blocks")
    assert k1["json"]["source"] == "M3_MAINTENANCE" and k1["json"]["ref_id"] == 7
    assert k1["json"]["end_at"] is None
    assert k1["idempotency_key"] == "m3-order-7-block"
    assert (m2, p2) == ("DELETE", "/internal/v1/blocks/M3_MAINTENANCE/7")
