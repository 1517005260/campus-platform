"""跨模块状态写回链路（任务书第二节）。M3、M2 的链路都已实现，这些测试是阻断部署的正式检查。"""

from datetime import timedelta

from time_helpers import day_at_iso, next_hour_iso

ROOM_ID = 1  # 演示数据：第三教学楼 H3106，允许整教室申请，每天 8–22 点开放


def _room_sources(http, headers, seat_id):
    history = http.get(f"/api/v1/seat/seats/{seat_id}/status-history", headers=headers).json()
    return {(h["source"], h["ref_id"], h["state"]) for h in history}


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


def test_m2_approval_occupies_room_and_withdraw_releases(http, login):
    applicant, dept_approver, school_approver, admin = (
        login("teacher"),
        login("dept_approver"),
        login("school_approver"),
        login("room_admin"),
    )
    # 固定在开放时间内：按运行时刻取下一个整点可能落在 22 点之后
    start, end = day_at_iso(3, 10), day_at_iso(3, 12)
    created = http.post(
        "/api/v1/room/applications",
        json={"room_id": ROOM_ID, "start_at": start, "end_at": end, "purpose": "集成测试", "attendees": 20},
        headers=applicant,
    )
    created.raise_for_status()
    app = created.json()
    for approver in (dept_approver, school_approver):
        http.post(
            f"/api/v1/room/applications/{app['id']}/approve", json={}, headers=approver
        ).raise_for_status()

    seat_id = http.get(f"/api/v1/seat/rooms/{ROOM_ID}", headers=applicant).json()["seats"][0]["id"]
    assert ("M2_OCCUPY", app["id"], "blocked") in _room_sources(http, admin, seat_id)

    http.post(f"/api/v1/room/applications/{app['id']}/withdraw", headers=applicant).raise_for_status()
    assert ("M2_OCCUPY", app["id"], "unblocked") in _room_sources(http, admin, seat_id)
