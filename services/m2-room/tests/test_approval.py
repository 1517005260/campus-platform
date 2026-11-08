"""多级审批、审批范围、截止时间、M1 占用与释放、撤回与取消、详情可见范围、待办。"""

from datetime import timedelta

import pytest
from app import clients, room_service
from app.models import Application, ApprovalRecord
from campus_common.errors import AppError
from campus_common.testing import NOW, record_service_calls
from sqlalchemy import select, update

from tests.conftest import (
    APPLICANT,
    DEPT_APPROVER,
    SCHOOL_APPROVER,
    body,
    headers,
    notifications,
    slot,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("m1_calls")]

BOTH_LEVELS = ["room:approve", "room:approve_school"]


def submit(client, as_applicant, **overrides) -> int:
    response = client.post("/api/v1/room/applications", json=body(**overrides), headers=as_applicant)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def act(client, application_id: int, action: str, as_user, comment: str | None = None):
    return client.post(
        f"/api/v1/room/applications/{application_id}/{action}", json={"comment": comment}, headers=as_user
    )


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def approved(client, as_applicant, as_dept_approver, as_school_approver, **overrides) -> int:
    application_id = submit(client, as_applicant, **overrides)
    assert act(client, application_id, "approve", as_dept_approver).status_code == 200
    assert act(client, application_id, "approve", as_school_approver).status_code == 200
    return application_id


def stored(db, application_id: int) -> Application:
    db.expire_all()
    return db.get(Application, application_id)


def set_columns(db, application_id: int, **values) -> None:
    db.execute(update(Application).where(Application.id == application_id).values(**values))
    db.commit()


# ---------- 多级流转 ----------


def test_two_levels_by_dept_then_school_approver_occupy_room_only_at_final_level(
    client, db, as_applicant, as_dept_approver, as_school_approver, m1_calls
):
    application_id = submit(client, as_applicant)
    m1_calls.clear()

    first = act(client, application_id, "approve", as_dept_approver, "院系同意")
    assert first.status_code == 200, first.text
    assert (first.json()["status"], first.json()["current_level"]) == ("pending", 2)
    assert first.json()["deadline_at"] == (NOW + timedelta(hours=48)).isoformat()
    assert m1_calls == []
    [level_done] = notifications(db, "room.level_approved")
    assert (level_done["user_ids"], level_done["params"]["level"], level_done["params"]["next_level"]) == (
        [APPLICANT],
        1,
        2,
    )
    [requested] = notifications(db, "room.approval_requested")
    assert (requested["perm"], requested["dept_id"], requested["user_ids"]) == (
        "room:approve_school",
        None,
        [],
    )
    assert (requested["params"]["level"], requested["params"]["applicant"]) == (2, "测试用户1001")

    final = act(client, application_id, "approve", as_school_approver, "学校同意")
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "approved"
    assert [(r["level"], r["approver"]["name"], r["comment"]) for r in final.json()["records"]] == [
        (1, "测试用户2001", "院系同意"),
        (2, "测试用户3001", "学校同意"),
    ]
    [(method, path, kwargs)] = m1_calls
    assert (method, path) == ("POST", "/internal/v1/blocks")
    assert kwargs["idempotency_key"] == f"m2-app-{application_id}-occupy"
    assert kwargs["json"] == {
        "room_id": 1,
        **slot(),
        "source": "M2_OCCUPY",
        "ref_id": application_id,
        "reason": "班级读书会",
    }
    assert (stored(db, application_id).m1_block_id, stored(db, application_id).occupy_requested_at) == (
        9,
        NOW,
    )
    [done] = notifications(db, "room.application_approved")
    assert done["user_ids"] == [APPLICANT]


def test_reject_at_any_level_notifies_applicant_with_level_and_comment(
    client, db, as_applicant, as_dept_approver, as_school_approver, m1_calls
):
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    rejected = act(client, application_id, "reject", as_school_approver, "活动说明不充分")
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["records"][-1]["action"] == "reject"
    [notice] = notifications(db, "room.application_rejected")
    assert (notice["user_ids"], notice["params"]["level"], notice["params"]["comment"]) == (
        [APPLICANT],
        2,
        "活动说明不充分",
    )
    assert [path for _, path, _ in m1_calls if "blocks" in path] == []
    assert error(act(client, application_id, "approve", as_school_approver)) == (
        409,
        "APPLICATION_STATE_CONFLICT",
    )


# ---------- 审批范围 ----------


def test_level_one_only_by_dept_approver_of_applicant_department(
    client, db, as_applicant, as_school_approver, as_other_dept_approver
):
    application_id = submit(client, as_applicant)
    # 学校级审批人能看到（能审批第 2 级），但不是当前级别的审批人
    assert error(act(client, application_id, "approve", as_school_approver)) == (403, "NOT_YOUR_TURN")
    # 其他院系的审批人哪一级都不能审批，看不到申请
    assert error(act(client, application_id, "approve", as_other_dept_approver)) == (404, "NOT_FOUND")
    no_dept = headers(2003, ["room:approve"], dept_id=None)
    assert error(act(client, application_id, "reject", no_dept)) == (404, "NOT_FOUND")


def test_level_two_needs_school_permission(client, db, as_applicant, as_dept_approver):
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    another_dept_approver = headers(2004, ["room:approve"])
    assert error(act(client, application_id, "approve", another_dept_approver)) == (403, "NOT_YOUR_TURN")


def test_same_person_cannot_approve_two_levels(client, db, as_applicant):
    both = headers(2005, BOTH_LEVELS)
    application_id = submit(client, as_applicant)
    assert act(client, application_id, "approve", both).status_code == 200
    assert error(act(client, application_id, "approve", both)) == (403, "NOT_YOUR_TURN")
    assert (
        act(client, application_id, "approve", headers(3002, ["room:approve_school"], None)).status_code
        == 200
    )


def test_applicant_cannot_approve_own_application(client, db):
    applicant = headers(APPLICANT, ["room:apply", *BOTH_LEVELS])
    application_id = submit(client, applicant)
    assert error(act(client, application_id, "approve", applicant)) == (403, "NOT_YOUR_TURN")
    assert error(act(client, application_id, "reject", applicant)) == (403, "NOT_YOUR_TURN")


# ---------- 截止时间 ----------


def test_approval_rejected_from_deadline_on(client, db, as_applicant, as_dept_approver):
    application_id = submit(client, as_applicant)
    set_columns(db, application_id, deadline_at=NOW + timedelta(microseconds=1))
    later = submit(client, as_applicant, **slot(3))
    set_columns(db, later, deadline_at=NOW)
    assert error(act(client, later, "approve", as_dept_approver)) == (409, "APPLICATION_EXPIRED")
    assert error(act(client, later, "reject", as_dept_approver)) == (409, "APPLICATION_EXPIRED")
    assert act(client, application_id, "approve", as_dept_approver).status_code == 200


def test_approval_rejected_once_slot_has_started(client, db, as_applicant, as_dept_approver):
    application_id = submit(client, as_applicant)
    set_columns(db, application_id, start_at=NOW)
    assert error(act(client, application_id, "approve", as_dept_approver)) == (409, "APPLICATION_EXPIRED")
    set_columns(db, application_id, start_at=NOW + timedelta(microseconds=1))
    assert act(client, application_id, "approve", as_dept_approver).status_code == 200


# ---------- 最终通过与 M1 ----------


def test_m1_failure_keeps_application_pending_and_records_the_attempt(
    client, db, as_applicant, as_dept_approver, as_school_approver, monkeypatch
):
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)

    async def unavailable(application):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr(clients, "occupy_room", unavailable)
    assert error(act(client, application_id, "approve", as_school_approver)) == (502, "UPSTREAM_UNAVAILABLE")
    application = stored(db, application_id)
    assert (application.status, application.current_level, application.occupy_requested_at) == (
        "pending",
        2,
        NOW,
    )
    assert db.scalar(select(ApprovalRecord.action).where(ApprovalRecord.level == 2)) is None
    assert notifications(db, "room.application_approved") == []


@pytest.mark.parametrize("concurrent_status", ["approved", "expired"])
def test_concurrent_change_during_occupy_returns_409_without_overwriting(
    client, db, as_applicant, as_dept_approver, as_school_approver, monkeypatch, concurrent_status
):
    """M1 占用期间另一操作已提交（并发的另一次最终审批，或超时撤销）：本次 409，不覆盖对方的结果。
    不在这里释放：对方通过时占用属于对方；对方使申请结束时由 release_leftover_blocks 释放。"""
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    occupy = clients.occupy_room

    async def occupy_while_other_commits(application):
        db.execute(
            update(Application)
            .where(Application.id == application.id)
            .values(status=concurrent_status, version=Application.version + 1)
        )
        db.commit()
        return await occupy(application)

    monkeypatch.setattr(clients, "occupy_room", occupy_while_other_commits)
    assert error(act(client, application_id, "approve", as_school_approver)) == (
        409,
        "APPLICATION_STATE_CONFLICT",
    )
    application = stored(db, application_id)
    assert (application.status, application.occupy_requested_at) == (concurrent_status, NOW)


def test_concurrent_final_approvers_conflict_before_calling_m1(
    client, db, as_applicant, as_dept_approver, as_school_approver, m1_calls, monkeypatch
):
    """两个学校级审批人同时最终审批：记录占用请求的提交按 version 冲突，后到的一方不调用 M1。"""
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    m1_calls.clear()
    check = room_service._check_turn

    async def other_approver_commits_first(session, user, application, at):
        await check(session, user, application, at)
        set_columns(db, application_id, occupy_requested_at=NOW, version=Application.version + 1)

    monkeypatch.setattr(room_service, "_check_turn", other_approver_commits_first)
    assert error(act(client, application_id, "approve", as_school_approver)) == (
        409,
        "APPLICATION_STATE_CONFLICT",
    )
    assert m1_calls == []


# ---------- 撤回与取消 ----------


def test_withdraw_pending_notifies_current_level_approvers_without_calling_m1(
    client, db, as_applicant, m1_calls
):
    application_id = submit(client, as_applicant)
    m1_calls.clear()
    withdrawn = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert withdrawn.json()["status"] == "withdrawn"
    assert m1_calls == []
    [notice] = notifications(db, "room.application_withdrawn")
    assert (notice["perm"], notice["dept_id"], notice["params"]["level"], notice["params"]["applicant"]) == (
        "room:approve",
        1,
        1,
        "测试用户1001",
    )


def test_only_applicant_can_withdraw(client, db, as_applicant):
    application_id = submit(client, as_applicant)
    approver_applicant = headers(DEPT_APPROVER, ["room:apply", "room:approve"])
    response = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=approver_applicant)
    assert error(response) == (403, "FORBIDDEN")


def test_cancel_approved_releases_first_and_notifies_its_approvers(
    client, db, as_applicant, as_dept_approver, as_school_approver, m1_calls
):
    application_id = approved(client, as_applicant, as_dept_approver, as_school_approver)
    m1_calls.clear()
    cancelled = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert cancelled.json()["status"] == "cancelled"
    assert [(m, p) for m, p, _ in m1_calls] == [("DELETE", f"/internal/v1/blocks/M2_OCCUPY/{application_id}")]
    assert stored(db, application_id).occupy_requested_at is None
    [notice] = notifications(db, "room.application_cancelled")
    assert (notice["user_ids"], notice["params"]["applicant"]) == (
        [DEPT_APPROVER, SCHOOL_APPROVER],
        "测试用户1001",
    )


def test_cancel_keeps_approved_when_m1_release_fails_and_retry_succeeds(
    client, db, as_applicant, as_dept_approver, as_school_approver, monkeypatch
):
    application_id = approved(client, as_applicant, as_dept_approver, as_school_approver)
    record_service_calls(monkeypatch, clients.m1, None)
    monkeypatch.setattr(clients.m1._http, "request", _raise_unavailable)
    response = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert error(response) == (502, "UPSTREAM_UNAVAILABLE")
    assert stored(db, application_id).status == "approved"

    # 上次已在 M1 释放（本地未提交）：重试时 M1 返回 released=false，照常完成取消
    record_service_calls(monkeypatch, clients.m1, {"released": False})
    retry = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert retry.json()["status"] == "cancelled"


async def _raise_unavailable(*args, **kwargs):
    raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")


def test_cancel_only_before_start(client, db, as_applicant, as_dept_approver, as_school_approver):
    application_id = approved(client, as_applicant, as_dept_approver, as_school_approver)
    set_columns(db, application_id, start_at=NOW)
    response = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert error(response) == (409, "APPLICATION_STATE_CONFLICT")
    set_columns(db, application_id, start_at=NOW + timedelta(microseconds=1))
    response = client.post(f"/api/v1/room/applications/{application_id}/withdraw", headers=as_applicant)
    assert response.json()["status"] == "cancelled"


# ---------- 查询 ----------


def test_detail_visible_to_applicant_and_possible_or_recorded_approvers_only(
    client, db, as_applicant, as_dept_approver, as_school_approver, as_other_dept_approver
):
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    url = f"/api/v1/room/applications/{application_id}"
    for viewer in (as_applicant, as_dept_approver, as_school_approver):
        assert client.get(url, headers=viewer).status_code == 200
    assert error(client.get(url, headers=as_other_dept_approver)) == (404, "NOT_FOUND")
    assert error(client.get(url, headers=headers(1009, ["room:apply"]))) == (404, "NOT_FOUND")
    # 审批过的人即使之后调到其他院系也能看到自己经手的申请
    moved = headers(DEPT_APPROVER, ["room:approve"], dept_id=2)
    assert client.get(url, headers=moved).status_code == 200


def test_mine_filters_by_status_and_paginates(client, db, as_applicant, as_dept_approver):
    first = submit(client, as_applicant)
    second = submit(client, as_applicant, **slot(3))
    act(client, first, "reject", as_dept_approver)
    submit(client, headers(1002, ["room:apply"]), **slot(4))

    page = client.get("/api/v1/room/applications/mine?size=1", headers=as_applicant).json()
    assert (page["total"], [item["id"] for item in page["items"]]) == (2, [second])
    rejected = client.get("/api/v1/room/applications/mine?status=rejected", headers=as_applicant).json()
    assert [item["id"] for item in rejected["items"]] == [first]
    assert rejected["items"][0]["records"][0]["action"] == "reject"


def test_todo_lists_only_what_the_user_can_act_on_now(
    client, db, as_applicant, as_dept_approver, as_school_approver, monkeypatch
):
    at_level_one = submit(client, as_applicant)
    at_level_two = submit(client, as_applicant, **slot(3))
    act(client, at_level_two, "approve", as_dept_approver)
    overdue = submit(client, as_applicant, **slot(4))
    set_columns(db, overdue, deadline_at=NOW)
    submit(client, headers(1002, ["room:apply"], dept_id=2), **slot(5))  # 其他院系
    record_service_calls(monkeypatch, clients.m1, [])  # 受影响预约数

    def todo(as_user):
        page = client.get("/api/v1/room/approvals/todo", headers=as_user).json()
        return page["total"], [item["id"] for item in page["items"]]

    assert todo(as_dept_approver) == (1, [at_level_one])
    assert todo(as_school_approver) == (1, [at_level_two])
    both = headers(2005, BOTH_LEVELS)
    assert todo(both) == (2, [at_level_one, at_level_two])
    # 审批过第 1 级的人不再看到该申请的第 2 级
    assert todo(headers(DEPT_APPROVER, BOTH_LEVELS)) == (1, [at_level_one])
    assert todo(headers(APPLICANT, ["room:apply", *BOTH_LEVELS])) == (0, [])


def test_todo_shows_affected_reservations_and_survives_m1_failure(
    client, db, as_applicant, as_dept_approver, monkeypatch
):
    application_id = submit(client, as_applicant)
    reservation = {"id": 5, "user_id": 7, "seat_id": 11, **slot(), "status": "reserved"}
    calls = record_service_calls(monkeypatch, clients.m1, [reservation, reservation | {"id": 6}])
    [item] = client.get("/api/v1/room/approvals/todo", headers=as_dept_approver).json()["items"]
    assert (item["id"], item["affected_reservations"]) == (application_id, 2)
    assert calls[0][1] == "/internal/v1/rooms/1/reservations"

    monkeypatch.setattr(clients.m1._http, "request", _raise_unavailable)
    response = client.get("/api/v1/room/approvals/todo", headers=as_dept_approver)
    assert response.status_code == 200
    assert response.json()["items"][0]["affected_reservations"] is None
