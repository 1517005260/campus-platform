"""跨模块状态写回链路（任务书第二节）。

这些测试在桩阶段会失败，所以先标记 xfail；对应链路实现后删除标记，
之后它们就是阻断部署的正式检查。
"""

from datetime import timedelta

import pytest
from time_helpers import next_hour_iso

PENDING = pytest.mark.xfail(reason="链路尚未实现；实现后删除此标记", strict=False)

ROOM_ID = 1  # 演示数据：第三教学楼 H3106，允许整教室申请


def _room_sources(http, headers, seat_id):
    history = http.get(f"/api/v1/seat/seats/{seat_id}/status-history", headers=headers).json()
    return {(h["source"], h["ref_id"], h["state"]) for h in history}


@PENDING
def test_m3_maintenance_blocks_and_restores_room(http, login):
    reporter, dispatcher, worker, admin = (
        login("student"),
        login("dispatcher"),
        login("worker"),
        login("room_admin"),
    )
    order = http.post(
        "/api/v1/repair/orders",
        json={"room_id": ROOM_ID, "category": "空调", "description": "集成测试：空调不制冷"},
        headers=reporter,
    ).json()
    worker_id = http.get("/api/v1/auth/me", headers=worker).json()["id"]
    http.post(
        f"/api/v1/repair/orders/{order['id']}/dispatch",
        json={"assignee_id": worker_id, "deadline_at": next_hour_iso(timedelta(days=1)), "blocks_room": True},
        headers=dispatcher,
    ).raise_for_status()
    http.post(f"/api/v1/repair/orders/{order['id']}/start", headers=worker).raise_for_status()

    seat_id = http.get(f"/api/v1/seat/rooms/{ROOM_ID}", headers=reporter).json()["seats"][0]["id"]
    assert ("M3_MAINTENANCE", order["id"], "blocked") in _room_sources(http, admin, seat_id)

    http.post(
        f"/api/v1/repair/orders/{order['id']}/complete", json={"note": "已修复"}, headers=worker
    ).raise_for_status()
    http.post(
        f"/api/v1/repair/orders/{order['id']}/accept", json={"rating": 5}, headers=reporter
    ).raise_for_status()
    assert ("M3_MAINTENANCE", order["id"], "unblocked") in _room_sources(http, admin, seat_id)


@PENDING
def test_m2_approval_occupies_room_and_withdraw_releases(http, login):
    applicant, dept_approver, school_approver, admin = (
        login("teacher"),
        login("dept_approver"),
        login("school_approver"),
        login("room_admin"),
    )
    start = next_hour_iso(timedelta(days=3))
    end = next_hour_iso(timedelta(days=3, hours=2))
    app = http.post(
        "/api/v1/room/applications",
        json={"room_id": ROOM_ID, "start_at": start, "end_at": end, "purpose": "集成测试", "attendees": 20},
        headers=applicant,
    ).json()
    for approver in (dept_approver, school_approver):
        http.post(
            f"/api/v1/room/applications/{app['id']}/approve", json={}, headers=approver
        ).raise_for_status()

    seat_id = http.get(f"/api/v1/seat/rooms/{ROOM_ID}", headers=applicant).json()["seats"][0]["id"]
    assert ("M2_OCCUPY", app["id"], "blocked") in _room_sources(http, admin, seat_id)

    http.post(f"/api/v1/room/applications/{app['id']}/withdraw", headers=applicant).raise_for_status()
    assert ("M2_OCCUPY", app["id"], "unblocked") in _room_sources(http, admin, seat_id)
