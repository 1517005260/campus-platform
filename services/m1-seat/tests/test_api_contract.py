"""接口层行为：鉴权、权限、参数校验、统一错误格式。

这些规则在桩阶段就已生效，替换成真实实现后仍必须成立。
"""


def test_public_endpoint_requires_login(client):
    resp = client.get("/api/v1/seat/rooms")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHENTICATED"


def test_reserve_requires_permission(client):
    from app.config import settings
    from campus_common.testing import user_headers

    headers = user_headers(settings, perms=["repair:report"])
    resp = client.post(
        "/api/v1/seat/reservations",
        json={"seat_id": 1, "date": "2026-10-20", "start_hour": 14, "end_hour": 16},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_reservation_rejects_reversed_hours(client, as_student):
    resp = client.post(
        "/api/v1/seat/reservations",
        json={"seat_id": 1, "date": "2026-10-20", "start_hour": 16, "end_hour": 14},
        headers=as_student,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_internal_rejects_user_token(client, as_student):
    resp = client.get("/internal/v1/rooms/1", headers=as_student)
    assert resp.status_code == 401
    assert resp.json()["code"] == "SERVICE_UNAUTHENTICATED"


def test_internal_rejects_wrong_service_key(client):
    resp = client.get(
        "/internal/v1/rooms/1", headers={"X-Service-Name": "m3-repair", "X-Service-Key": "wrong"}
    )
    assert resp.status_code == 401


def test_violation_count_only_for_m2(client, as_m3):
    resp = client.get("/internal/v1/users/1/violations?since=2026-10-01T00:00:00%2B08:00", headers=as_m3)
    assert resp.status_code == 403
    assert resp.json()["code"] == "SERVICE_FORBIDDEN"


def test_block_requires_idempotency_key(client):
    from tests.conftest import M3_KEY

    resp = client.post(
        "/internal/v1/blocks",
        json={
            "room_id": 1,
            "start_at": "2026-10-20T08:00:00+08:00",
            "source": "M3_MAINTENANCE",
            "ref_id": 7,
            "reason": "空调维修",
        },
        headers={"X-Service-Name": "m3-repair", "X-Service-Key": M3_KEY},
    )
    assert resp.status_code == 422


def test_block_rejects_naive_datetime(client, as_m3):
    resp = client.post(
        "/internal/v1/blocks",
        json={
            "room_id": 1,
            "start_at": "2026-10-20T08:00:00",
            "source": "M3_MAINTENANCE",
            "ref_id": 7,
            "reason": "空调维修",
        },
        headers=as_m3,
    )
    assert resp.status_code == 422


def test_request_id_is_echoed(client, as_student):
    resp = client.get("/api/v1/seat/rooms", headers={**as_student, "X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"
