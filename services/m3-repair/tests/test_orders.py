"""工单状态机：上报、派单、维修、验收、代验收、权限与 M1 下架/恢复。时间由冻结的时钟注入。"""

from datetime import timedelta

import pytest
from app import clients
from app.config import settings
from app.models import Outbox, WorkOrder
from campus_common.auth import CurrentUser, create_token
from campus_common.errors import AppError
from campus_common.testing import NOW, user_headers
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from tests.conftest import DISPATCHER_ID, MANAGER_ID, REPORTER_ID, WORKER_ID

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("db")]

ORDERS = "/api/v1/repair/orders"
BLOCK_KEY = "m3-order-{}-block"


def report(client, headers, **extra):
    resp = client.post(
        ORDERS, json={"room_id": 3, "category": "空调", "description": "不制冷"} | extra, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def dispatch(client, headers, order_id, *, blocks_room=False, assignee_id=WORKER_ID, deadline=None):
    return client.post(
        f"{ORDERS}/{order_id}/dispatch",
        json={
            "assignee_id": assignee_id,
            "deadline_at": (deadline or NOW + timedelta(days=1)).isoformat(),
            "blocks_room": blocks_room,
        },
        headers=headers,
    )


def act(client, headers, order_id, action, body=None):
    return client.post(f"{ORDERS}/{order_id}/{action}", json=body, headers=headers)


def to_pending(client, as_reporter, as_dispatcher, as_worker, *, blocks_room=False) -> int:
    order_id = report(client, as_reporter)
    assert dispatch(client, as_dispatcher, order_id, blocks_room=blocks_room).status_code == 200
    assert act(client, as_worker, order_id, "start").status_code == 200
    assert act(client, as_worker, order_id, "complete", {"note": "已更换压缩机"}).status_code == 200
    return order_id


def status_of(db, order_id) -> str:
    db.expire_all()
    return db.scalar(select(WorkOrder.status).where(WorkOrder.id == order_id))


def notices(db, template) -> list[dict]:
    db.expire_all()
    rows = db.scalars(select(Outbox).where(Outbox.type == "notification.send")).all()
    return [row.envelope["payload"] for row in rows if row.envelope["payload"]["template"] == template]


def m1_writes(calls) -> list[tuple[str, str]]:
    return [(method, path) for method, path, _ in calls if not path.startswith("/internal/v1/rooms/")]


# ---------- 完整流转 ----------


def test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, m1_calls
):
    order_id = report(client, as_reporter)
    assert dispatch(client, as_dispatcher, order_id, blocks_room=True).json()["status"] == "dispatched"

    started = act(client, as_worker, order_id, "start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    (_, path, call), *_ = [c for c in m1_calls if c[0] == "POST"]
    assert path == "/internal/v1/blocks"
    assert call["idempotency_key"] == BLOCK_KEY.format(order_id)
    assert call["json"] == {
        "room_id": 3,
        "start_at": NOW.isoformat(),
        "end_at": None,
        "source": "M3_MAINTENANCE",
        "ref_id": order_id,
        "reason": f"报修工单 #{order_id} 维修中",
    }

    assert (
        act(client, as_worker, order_id, "complete", {"note": "已更换"}).json()["status"]
        == "pending_acceptance"
    )
    assert act(client, as_reporter, order_id, "reject-acceptance", {"reason": "仍不制冷"}).json()[
        "status"
    ] == ("in_progress")
    assert m1_writes(m1_calls) == [("POST", "/internal/v1/blocks")]  # 退回维修时教室保持下架

    act(client, as_worker, order_id, "complete", {"note": "再次更换"})
    accepted = act(client, as_reporter, order_id, "accept", {"rating": 5, "comment": "好了"})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert (body["status"], body["rating"]) == ("closed", 5)
    assert m1_writes(m1_calls) == [
        ("POST", "/internal/v1/blocks"),
        ("DELETE", f"/internal/v1/blocks/M3_MAINTENANCE/{order_id}"),
    ]
    assert [(i["action"], i["from_status"], i["to_status"]) for i in body["timeline"]] == [
        ("report", None, "submitted"),
        ("dispatch", "submitted", "dispatched"),
        ("start", "dispatched", "in_progress"),
        ("complete", "in_progress", "pending_acceptance"),
        ("reject", "pending_acceptance", "in_progress"),
        ("complete", "in_progress", "pending_acceptance"),
        ("accept", "pending_acceptance", "closed"),
    ]
    assert [i["actor"]["id"] for i in body["timeline"]] == [
        REPORTER_ID,
        DISPATCHER_ID,
        WORKER_ID,
        WORKER_ID,
        REPORTER_ID,
        WORKER_ID,
        REPORTER_ID,
    ]


def test_each_step_notifies_the_right_people_with_template_params(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls
):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id, blocks_room=True)
    act(client, as_worker, order_id, "start")
    act(client, as_worker, order_id, "complete", {"note": "已更换压缩机"})
    act(client, as_reporter, order_id, "reject-acceptance", {"reason": "仍不制冷"})
    act(client, as_worker, order_id, "complete", {"note": "再次更换"})
    act(client, as_reporter, order_id, "accept", {"rating": 4})

    base = {"order_id": order_id, "category": "空调"}
    (reported,) = notices(db, "repair.reported")
    assert (reported["user_ids"], reported["perm"]) == ([], "repair:dispatch")
    assert reported["params"] == base | {"room": "第三教学楼 H3106"}
    (dispatched,) = notices(db, "repair.dispatched")
    assert dispatched["user_ids"] == [WORKER_ID]
    assert dispatched["params"] == base | {
        "deadline_at": (NOW + timedelta(days=1)).isoformat(),
        "blocks_room": True,
    }
    (started,) = notices(db, "repair.started")
    assert (started["user_ids"], started["params"]) == ([REPORTER_ID], base | {"blocks_room": True})
    first, _ = notices(db, "repair.completed")
    assert first["user_ids"] == [REPORTER_ID]
    assert first["params"] == base | {"note": "已更换压缩机", "accept_after_hours": 72}
    (rejected,) = notices(db, "repair.rejected")
    assert (rejected["user_ids"], rejected["params"]) == (
        [WORKER_ID],
        base | {"reason": "仍不制冷", "blocks_room": True},
    )
    (accepted,) = notices(db, "repair.accepted")
    assert (accepted["user_ids"], accepted["params"]) == (
        [WORKER_ID],
        base | {"rating": 4, "by_admin": False},
    )


def test_room_not_blocked_never_calls_m1_block_or_release(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, m1_calls
):
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker, blocks_room=False)
    assert act(client, as_reporter, order_id, "accept", {"rating": 5}).json()["status"] == "closed"
    assert m1_writes(m1_calls) == []


# ---------- 上报与配置 ----------


def test_report_unknown_room_is_400_room_not_found(client, db, as_reporter, monkeypatch):
    async def missing(room_id):
        raise AppError(404, "NOT_FOUND", f"教室 {room_id} 不存在")

    monkeypatch.setattr(clients.m1, "get_room", missing)
    resp = client.post(
        ORDERS, json={"room_id": 99, "category": "空调", "description": "不制冷"}, headers=as_reporter
    )
    assert (resp.status_code, resp.json()["code"]) == (400, "ROOM_NOT_FOUND")
    assert db.scalar(select(WorkOrder.id)) is None


def test_report_when_m1_unreachable_is_502(client, db, as_reporter, monkeypatch):
    async def down(room_id):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr(clients.m1, "get_room", down)
    resp = client.post(
        ORDERS, json={"room_id": 3, "category": "空调", "description": "不制冷"}, headers=as_reporter
    )
    assert (resp.status_code, resp.json()["code"]) == (502, "UPSTREAM_UNAVAILABLE")


@pytest.mark.parametrize("seat_id", [None, 11, 12])
def test_report_accepts_no_seat_or_a_seat_of_the_room(client, db, as_reporter, m1_calls, seat_id):
    order_id = report(client, as_reporter, seat_id=seat_id)
    assert db.scalar(select(WorkOrder.seat_id).where(WorkOrder.id == order_id)) == seat_id


@pytest.mark.parametrize("seat_id", [10, 13, 9999])
def test_report_rejects_seat_outside_the_room(client, db, as_reporter, m1_calls, seat_id):
    resp = client.post(
        ORDERS,
        json={"room_id": 3, "seat_id": seat_id, "category": "空调", "description": "不制冷"},
        headers=as_reporter,
    )
    assert (resp.status_code, resp.json()["code"]) == (400, "SEAT_NOT_IN_ROOM")
    assert db.scalar(select(WorkOrder.id)) is None


def _rule(status="dispatched", timeout_hours=24, **extra) -> dict:
    return {"status": status, "timeout_hours": timeout_hours} | extra


@pytest.mark.parametrize(
    "change",
    [
        {"escalation_rules": [_rule(), _rule(timeout_hours=48)]},
        {"escalation_rules": [_rule(timeout_hours=0)]},
        {"escalation_rules": [_rule(notify_perm="")]},
        {"escalation_rules": [_rule(notify_perm="管理员")]},
        {"escalation_rules": [_rule(notify_perm="repair")]},
        {"escalation_rules": [_rule(notify_perm="seat:stats")]},
        {"categories": []},
        {"categories": [""]},
        {"categories": ["  "]},
        {"categories": ["x" * 31]},
        {"categories": ["空调", " 空调 "]},
        {"admin_accept_after_hours": 0},
        {"admin_accept_after_hours": -1},
    ],
)
def test_settings_reject_invalid_values_and_keep_current(client, db, as_manager, change):
    current = client.get("/api/v1/repair/settings", headers=as_manager).json()
    resp = client.put("/api/v1/repair/settings", json=current | change, headers=as_manager)
    assert (resp.status_code, resp.json()["code"]) == (422, "VALIDATION_ERROR")
    assert client.get("/api/v1/repair/settings", headers=as_manager).json() == current


def test_settings_accept_values_at_the_limits(client, db, as_manager):
    body = {
        "categories": [" 电梯 ", "x" * 30],
        "escalation_rules": [_rule(timeout_hours=1, notify_perm="repair:dispatch")],
        "admin_accept_after_hours": 1,
    }
    resp = client.put("/api/v1/repair/settings", json=body, headers=as_manager)
    assert resp.status_code == 200, resp.text
    saved = client.get("/api/v1/repair/settings", headers=as_manager).json()
    assert saved == body | {"categories": ["电梯", "x" * 30]}


def test_settings_categories_drive_report_validation(client, db, as_reporter, as_manager):
    current = client.get("/api/v1/repair/settings", headers=as_reporter).json()
    assert client.put("/api/v1/repair/settings", json=current, headers=as_reporter).status_code == 403
    saved = client.put("/api/v1/repair/settings", json=current | {"categories": ["电梯"]}, headers=as_manager)
    assert saved.status_code == 200, saved.text

    assert report(client, as_reporter, category="电梯")
    old = client.post(
        ORDERS, json={"room_id": 3, "category": "空调", "description": "不制冷"}, headers=as_reporter
    )
    assert (old.status_code, old.json()["code"]) == (400, "UNKNOWN_CATEGORY")


# ---------- 取消 ----------


def test_cancel_only_by_reporter_before_dispatch_and_notifies_dispatchers(
    client, db, as_reporter, as_dispatcher, common_calls
):
    order_id = report(client, as_reporter)
    other = user_headers(settings, perms=["repair:report"], user_id=1002)
    assert act(client, other, order_id, "cancel", {"reason": "不修了"}).status_code == 404
    staff = user_headers(settings, perms=["repair:report", "repair:dispatch"], user_id=DISPATCHER_ID)
    resp = act(client, staff, order_id, "cancel", {"reason": "不修了"})
    assert (resp.status_code, resp.json()["code"]) == (403, "FORBIDDEN")

    cancelled = act(client, as_reporter, order_id, "cancel", {"reason": " 已自行修好 "})
    assert cancelled.json()["status"] == "cancelled"
    (notice,) = notices(db, "repair.cancelled")
    assert (notice["user_ids"], notice["perm"]) == ([], "repair:dispatch")
    assert notice["params"] == {"order_id": order_id, "category": "空调", "reason": "已自行修好"}

    again = act(client, as_reporter, order_id, "cancel", {"reason": "再取消"})
    assert (again.status_code, again.json()["code"]) == (409, "ORDER_STATE_CONFLICT")


def test_cancel_after_dispatch_is_rejected(client, db, as_reporter, as_dispatcher, common_calls):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id)
    resp = act(client, as_reporter, order_id, "cancel", {"reason": "不修了"})
    assert (resp.status_code, resp.json()["code"]) == (409, "ORDER_STATE_CONFLICT")
    assert resp.json()["message"] == "工单当前为“已派单”，不能执行此操作"
    assert status_of(db, order_id) == "dispatched"


@pytest.mark.parametrize("text", ["", "   ", "修", " 修 "])
def test_reason_and_note_need_two_non_blank_characters(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, text
):
    submitted = report(client, as_reporter)
    pending = to_pending(client, as_reporter, as_dispatcher, as_worker)
    in_progress = report(client, as_reporter)
    dispatch(client, as_dispatcher, in_progress)
    act(client, as_worker, in_progress, "start")

    responses = [
        client.post(
            ORDERS, json={"room_id": 3, "category": "空调", "description": text}, headers=as_reporter
        ),
        act(client, as_reporter, submitted, "cancel", {"reason": text}),
        act(client, as_worker, in_progress, "complete", {"note": text}),
        act(client, as_reporter, pending, "reject-acceptance", {"reason": text}),
    ]
    assert [resp.status_code for resp in responses] == [422] * 4
    assert [status_of(db, i) for i in (submitted, in_progress, pending)] == [
        "submitted",
        "in_progress",
        "pending_acceptance",
    ]


# ---------- 派单 ----------


def test_dispatch_requires_assignee_with_repair_work(client, db, as_reporter, as_dispatcher, common_calls):
    order_id = report(client, as_reporter)
    resp = dispatch(client, as_dispatcher, order_id, assignee_id=3002)
    assert (resp.status_code, resp.json()["code"]) == (400, "ASSIGNEE_NOT_WORKER")
    assert status_of(db, order_id) == "submitted"
    assert common_calls[-1][:2] == ("GET", "/internal/v1/users")
    assert common_calls[-1][2]["params"] == {"perm": "repair:work"}

    ok = dispatch(client, as_dispatcher, order_id)
    assert ok.status_code == 200, ok.text
    assert ok.json()["assignee"] == {"id": WORKER_ID, "username": "worker", "name": "王师傅", "dept_id": None}


@pytest.mark.parametrize(("offset", "expected"), [(timedelta(0), 400), (timedelta(seconds=1), 200)])
def test_dispatch_deadline_must_be_in_future(
    client, db, as_reporter, as_dispatcher, common_calls, offset, expected
):
    order_id = report(client, as_reporter)
    resp = dispatch(client, as_dispatcher, order_id, deadline=NOW + offset)
    assert resp.status_code == expected, resp.text
    if expected == 400:
        assert resp.json()["code"] == "DEADLINE_NOT_FUTURE"


def test_dispatch_deadline_given_in_utc_is_returned_in_business_time_zone(
    client, db, as_reporter, as_dispatcher, common_calls
):
    order_id = report(client, as_reporter)
    resp = client.post(
        f"{ORDERS}/{order_id}/dispatch",
        json={"assignee_id": WORKER_ID, "deadline_at": "2026-10-20T10:00:00Z", "blocks_room": False},
        headers=as_dispatcher,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deadline_at"] == "2026-10-20T18:00:00+08:00"
    (dispatched,) = notices(db, "repair.dispatched")
    assert dispatched["params"]["deadline_at"] == "2026-10-20T18:00:00+08:00"


def test_dispatch_only_from_submitted(client, db, as_reporter, as_dispatcher, common_calls):
    order_id = report(client, as_reporter)
    assert dispatch(client, as_dispatcher, order_id).status_code == 200
    again = dispatch(client, as_dispatcher, order_id)
    assert (again.status_code, again.json()["code"]) == (409, "ORDER_STATE_CONFLICT")

    cancelled = report(client, as_reporter)
    act(client, as_reporter, cancelled, "cancel", {"reason": "不修了"})
    assert dispatch(client, as_dispatcher, cancelled).status_code == 409


# ---------- 开始与完工 ----------


def test_only_assignee_starts_and_completes(client, db, as_reporter, as_dispatcher, as_worker, common_calls):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id)
    other_worker = user_headers(settings, perms=["repair:work"], user_id=3002)
    # 看得到工单（兼调度）但不是被指派人：403；看不到工单的维修工：404，不暴露工单是否存在
    lead = user_headers(settings, perms=["repair:work", "repair:dispatch"], user_id=3003)

    assert act(client, other_worker, order_id, "start").status_code == 404
    resp = act(client, lead, order_id, "start")
    assert (resp.status_code, resp.json()["code"]) == (403, "NOT_ASSIGNEE")
    assert act(client, as_worker, order_id, "start").status_code == 200

    assert act(client, other_worker, order_id, "complete", {"note": "已修好"}).status_code == 404
    resp = act(client, lead, order_id, "complete", {"note": "已修好"})
    assert (resp.status_code, resp.json()["code"]) == (403, "NOT_ASSIGNEE")
    assert status_of(db, order_id) == "in_progress"
    assert act(client, as_worker, order_id, "complete", {"note": "好了"}).status_code == 200


def test_start_and_complete_require_matching_state(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls
):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id)
    assert act(client, as_worker, order_id, "complete", {"note": "已修好"}).status_code == 409
    act(client, as_worker, order_id, "start")
    resp = act(client, as_worker, order_id, "start")
    assert (resp.status_code, resp.json()["code"]) == (409, "ORDER_STATE_CONFLICT")


def test_m1_block_failure_keeps_order_dispatched(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, monkeypatch
):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id, blocks_room=True)

    async def down(*_args, **_kwargs):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr(clients, "block_room", down)
    resp = act(client, as_worker, order_id, "start")
    assert (resp.status_code, resp.json()["code"]) == (502, "UPSTREAM_UNAVAILABLE")
    assert status_of(db, order_id) == "dispatched"
    assert notices(db, "repair.started") == []


def test_start_retry_after_lost_m1_response_sends_identical_request(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, m1_calls, clock, monkeypatch
):
    """第一次下架已到达 M1 但响应丢失（超时）。重试必须发出完全相同的请求，否则 M1 按幂等键
    返回 409 IDEMPOTENCY_KEY_REUSED，工单永远停在 dispatched、教室却已下架。"""
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id, blocks_room=True)
    block_room = clients.block_room

    async def response_lost(*args, **kwargs):
        await block_room(*args, **kwargs)
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "调用 M1 超时")

    monkeypatch.setattr(clients, "block_room", response_lost)
    assert act(client, as_worker, order_id, "start").status_code == 502
    assert status_of(db, order_id) == "dispatched"

    monkeypatch.setattr(clients, "block_room", block_room)
    clock.shift(timedelta(minutes=3))
    retried = act(client, as_worker, order_id, "start")
    assert retried.status_code == 200, retried.text
    first, second = [kwargs for method, _, kwargs in m1_calls if method == "POST"]
    assert second == first
    assert first["json"]["start_at"] == NOW.isoformat()
    assert status_of(db, order_id) == "in_progress"


# ---------- 验收 ----------


def test_only_reporter_may_reject(client, db, as_reporter, as_dispatcher, as_worker, common_calls):
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker)
    other = user_headers(settings, perms=["repair:report"], user_id=1002)
    assert act(client, other, order_id, "reject-acceptance", {"reason": "仍有故障"}).status_code == 404
    # 能看到工单（兼调度）的其他报修人：403
    staff = user_headers(settings, perms=["repair:report", "repair:dispatch"], user_id=DISPATCHER_ID)
    resp = act(client, staff, order_id, "reject-acceptance", {"reason": "仍有故障"})
    assert (resp.status_code, resp.json()["code"]) == (403, "FORBIDDEN")
    assert status_of(db, order_id) == "pending_acceptance"
    assert act(client, as_reporter, order_id, "reject-acceptance", {"reason": "仍有故障"}).status_code == 200


def test_accept_by_other_reporter_is_404_like_other_endpoints(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls
):
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker)
    other = user_headers(settings, perms=["repair:report"], user_id=1002)
    resp = act(client, other, order_id, "accept", {"rating": 5})
    assert (resp.status_code, resp.json()["code"]) == (404, "NOT_FOUND")
    assert status_of(db, order_id) == "pending_acceptance"


def test_accept_only_from_pending_acceptance_and_room_stays_blocked(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, m1_calls
):
    order_id = report(client, as_reporter)
    dispatch(client, as_dispatcher, order_id, blocks_room=True)
    act(client, as_worker, order_id, "start")
    resp = act(client, as_reporter, order_id, "accept", {"rating": 5})
    assert (resp.status_code, resp.json()["code"]) == (409, "ORDER_STATE_CONFLICT")
    assert m1_writes(m1_calls) == [("POST", "/internal/v1/blocks")]  # 维修中的教室没有被恢复


@pytest.mark.parametrize(
    ("completed_ago", "expected"),
    [
        (timedelta(hours=72) - timedelta(seconds=1), 403),
        (timedelta(hours=72), 200),
    ],
)
def test_manager_accepts_only_after_waiting_period(
    client, db, as_reporter, as_dispatcher, as_worker, as_manager, common_calls, completed_ago, expected
):
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker)
    db.execute(update(WorkOrder).where(WorkOrder.id == order_id).values(completed_at=NOW - completed_ago))
    db.commit()

    resp = act(client, as_manager, order_id, "accept", {"rating": 3})
    assert resp.status_code == expected, resp.text
    db.expire_all()
    order = db.get(WorkOrder, order_id)
    if expected == 403:
        assert resp.json()["code"] == "ADMIN_ACCEPT_TOO_EARLY"
        assert (order.status, order.closed_by) == ("pending_acceptance", None)
    else:
        assert (order.status, order.closed_by, order.rating) == ("closed", MANAGER_ID, 3)
        assert resp.json()["timeline"][-1]["action"] == "admin_accept"
        (notice,) = notices(db, "repair.accepted")
        assert notice["params"]["by_admin"] is True


def test_m1_release_failure_keeps_pending_then_retry_closes(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, m1_calls, monkeypatch
):
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker, blocks_room=True)

    async def down(order_id):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    release_room = clients.release_room
    monkeypatch.setattr(clients, "release_room", down)
    resp = act(client, as_reporter, order_id, "accept", {"rating": 5})
    assert (resp.status_code, resp.json()["code"]) == (502, "UPSTREAM_UNAVAILABLE")
    db.expire_all()
    order = db.get(WorkOrder, order_id)
    assert (order.status, order.rating, order.closed_by) == ("pending_acceptance", None, None)
    assert notices(db, "repair.accepted") == []

    monkeypatch.setattr(clients, "release_room", release_room)
    assert act(client, as_reporter, order_id, "accept", {"rating": 5}).json()["status"] == "closed"
    assert m1_writes(m1_calls)[-1] == ("DELETE", f"/internal/v1/blocks/M3_MAINTENANCE/{order_id}")


def test_accept_keeps_order_locked_while_releasing_room(
    client, db, as_reporter, as_dispatcher, as_worker, common_calls, monkeypatch
):
    """释放教室期间工单行保持锁定：并发的"验收不通过"只能等验收完成后再判断状态，
    不会出现教室已在 M1 恢复、工单却退回维修中的情况（M1 中已释放的占用不能再用同一单号下架）。"""
    order_id = to_pending(client, as_reporter, as_dispatcher, as_worker, blocks_room=True)
    seen: list[str] = []

    async def release_and_probe(order_id):
        try:
            db.execute(text("SET LOCAL lock_timeout = '100ms'"))
            db.execute(select(WorkOrder.id).where(WorkOrder.id == order_id).with_for_update(nowait=True))
            seen.append("unlocked")
        except OperationalError:
            seen.append("locked")
        finally:
            db.rollback()
        return True

    monkeypatch.setattr(clients, "release_room", release_and_probe)
    assert act(client, as_reporter, order_id, "accept", {"rating": 5}).status_code == 200
    assert seen == ["locked"]


# ---------- 查询 ----------


def test_reads_show_people_without_calling_common(
    client, db, as_reporter, as_dispatcher, as_worker, as_manager, common_calls
):
    first = report(client, as_reporter)
    second = report(client, as_reporter)
    dispatch(client, as_dispatcher, first)
    calls_before = len(common_calls)

    page = client.get(ORDERS, headers=as_manager).json()
    assert [item["id"] for item in page["items"]] == [second, first]
    assert page["total"] == 2
    item = page["items"][1]
    assert item["reporter"] == {"id": REPORTER_ID, "username": "u1001", "name": "测试用户1001", "dept_id": 1}
    assert item["assignee"]["name"] == "王师傅"
    assert item["timeline"][1]["actor"]["name"] == f"测试用户{DISPATCHER_ID}"
    assert client.get(f"{ORDERS}/{first}", headers=as_reporter).json()["assignee"]["name"] == "王师傅"
    assert client.get(f"{ORDERS}/mine", headers=as_reporter).json()["total"] == 2
    assert len(common_calls) == calls_before  # 读接口不依赖 common


def test_snapshot_name_refreshes_when_user_acts_again(client, db, as_reporter):
    order_id = report(client, as_reporter)
    renamed = CurrentUser(
        id=REPORTER_ID, username="u1001", name="改名后", dept_id=2, roles=["test"], perms=["repair:report"]
    )
    headers = {"Authorization": f"Bearer {create_token(renamed, settings)}"}
    body = act(client, headers, order_id, "cancel", {"reason": "不修了"}).json()
    assert body["reporter"] == {"id": REPORTER_ID, "username": "u1001", "name": "改名后", "dept_id": 2}
    assert {item["actor"]["name"] for item in body["timeline"]} == {"改名后"}


def test_list_filters_and_worker_sees_only_assigned(
    client, db, as_reporter, as_dispatcher, as_worker, as_manager, common_calls
):
    first = report(client, as_reporter)
    second = report(client, as_reporter)
    dispatch(client, as_dispatcher, first)
    db.execute(update(WorkOrder).where(WorkOrder.id == second).values(escalation_level=1))
    db.commit()

    def ids(headers, **query):
        resp = client.get(ORDERS, params=query, headers=headers)
        assert resp.status_code == 200, resp.text
        return [item["id"] for item in resp.json()["items"]]

    assert ids(as_worker) == [first]
    assert ids(as_manager, status="submitted") == [second]
    assert ids(as_manager, assignee_id=WORKER_ID) == [first]
    assert ids(as_manager, escalated=True) == [second]
    assert ids(as_manager, escalated=False) == [first]
    assert ids(as_manager, room_id=4) == []
    assert client.get(f"{ORDERS}/{second}", headers=as_worker).status_code == 404
    other = user_headers(settings, perms=["repair:report"], user_id=1002)
    assert client.get(f"{ORDERS}/{first}", headers=other).status_code == 404
    assert client.get(f"{ORDERS}/mine", headers=other).json()["total"] == 0
