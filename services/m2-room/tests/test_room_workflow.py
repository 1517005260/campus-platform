"""M2 申请、审批、撤回与超时状态机。"""

from datetime import timedelta

import pytest
from app import clients
from app.jobs import expire_overdue
from app.models import Application, ApprovalRecord
from campus_common.errors import AppError
from campus_common.testing import user_headers
from campus_common.timeutil import now
from sqlalchemy import func, select

pytestmark = pytest.mark.db


def application_body(*, room_id: int = 1, start_offset: timedelta = timedelta(days=2)):
    start = now() + start_offset
    return {
        "room_id": room_id,
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=2)).isoformat(),
        "purpose": "班级读书会",
        "attendees": 30,
    }


def submit(client, as_applicant, **kwargs):
    response = client.post(
        "/api/v1/room/applications",
        json=application_body(**kwargs),
        headers=as_applicant,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_submit_snapshots_flow_and_rejects_overlap(client, db, as_applicant):
    created = submit(client, as_applicant)
    assert created["status"] == "pending"
    assert created["current_level"] == 1
    assert created["total_levels"] == 2

    conflict = client.post(
        "/api/v1/room/applications",
        json=application_body(start_offset=timedelta(days=2, hours=1)),
        headers=as_applicant,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "APPLICATION_TIME_CONFLICT"

    stored = db.get(Application, created["id"])
    assert [level["scope"] for level in stored.flow_snapshot] == ["dept", "school"]


def test_two_level_approval_occupies_room_only_at_final_level(client, db, as_applicant, as_approver):
    created = submit(client, as_applicant)

    first = client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={"comment": "院系同意"},
        headers=as_approver,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    assert first.json()["current_level"] == 2

    final = client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={"comment": "学校同意"},
        headers=as_approver,
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "approved"
    assert [record["action"] for record in final.json()["records"]] == ["approve", "approve"]

    db.expire_all()
    stored = db.get(Application, created["id"])
    assert stored.m1_block_id == created["id"]


def test_approver_cannot_approve_own_or_other_department_application(client, db, as_applicant, as_approver):
    created = submit(client, as_applicant)
    own = client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={},
        headers=user_headers(
            clients.settings,
            perms=["room:apply", "room:approve"],
            user_id=1001,
            dept_id=1,
        ),
    )
    assert own.status_code == 403
    assert own.json()["code"] == "NOT_YOUR_TURN"

    other_department = client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={},
        headers=user_headers(clients.settings, perms=["room:approve"], user_id=2002, dept_id=2),
    )
    assert other_department.status_code == 403
    assert other_department.json()["code"] == "NOT_YOUR_TURN"


def test_final_approval_keeps_pending_when_m1_fails(client, db, as_applicant, as_approver, monkeypatch):
    created = submit(client, as_applicant)
    client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={},
        headers=as_approver,
    )

    async def fail(*args, **kwargs):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr(clients, "occupy_room", fail)
    response = client.post(
        f"/api/v1/room/applications/{created['id']}/approve",
        json={},
        headers=as_approver,
    )
    assert response.status_code == 502
    db.expire_all()
    assert db.get(Application, created["id"]).status == "pending"


def test_withdraw_pending_does_not_release_and_cancel_approved_does(
    client, db, as_applicant, as_approver, monkeypatch
):
    released = []

    async def release(application_id):
        released.append(application_id)
        return True

    monkeypatch.setattr(clients, "release_room", release)
    pending = submit(client, as_applicant)
    withdrawn = client.post(f"/api/v1/room/applications/{pending['id']}/withdraw", headers=as_applicant)
    assert withdrawn.json()["status"] == "withdrawn"
    assert released == []

    approved = submit(client, as_applicant, room_id=2)
    for _ in range(2):
        response = client.post(
            f"/api/v1/room/applications/{approved['id']}/approve",
            json={},
            headers=as_approver,
        )
        assert response.status_code == 200, response.text
    cancelled = client.post(f"/api/v1/room/applications/{approved['id']}/withdraw", headers=as_applicant)
    assert cancelled.json()["status"] == "cancelled"
    assert released == [approved["id"]]


def test_expire_overdue_uses_inclusive_deadline_and_is_idempotent(client, db, as_applicant):
    created = submit(client, as_applicant)
    db.expire_all()
    application = db.get(Application, created["id"])

    assert expire_overdue(db, application.deadline_at - timedelta(microseconds=1)) == []
    assert expire_overdue(db, application.deadline_at) == [application.id]
    db.commit()
    assert expire_overdue(db, application.deadline_at + timedelta(minutes=1)) == []
    assert (
        db.scalar(
            select(func.count())
            .select_from(ApprovalRecord)
            .where(
                ApprovalRecord.application_id == application.id,
                ApprovalRecord.action == "expire",
            )
        )
        == 1
    )


def test_todo_reject_and_mine_filter(client, db, as_applicant, as_approver):
    created = submit(client, as_applicant)
    todo = client.get("/api/v1/room/approvals/todo", headers=as_approver)
    assert todo.status_code == 200
    assert todo.json()["total"] == 1
    assert todo.json()["items"][0]["affected_reservations"] == 0

    rejected = client.post(
        f"/api/v1/room/applications/{created['id']}/reject",
        json={"comment": "活动说明不充分"},
        headers=as_approver,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["records"][0]["comment"] == "活动说明不充分"

    mine = client.get("/api/v1/room/applications/mine?status=rejected", headers=as_applicant)
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()["items"]] == [created["id"]]


def test_flow_changes_only_affect_new_applications_and_settings_persist(
    client, db, as_applicant, as_flow_manager
):
    existing = submit(client, as_applicant)
    replacement = [
        {
            "name": "单级审批",
            "room_type": None,
            "dept_scoped": None,
            "priority": 10,
            "levels": [
                {
                    "level": 1,
                    "approver_perm": "room:approve",
                    "scope": "school",
                    "timeout_hours": 24,
                }
            ],
        }
    ]
    changed = client.put("/api/v1/room/flows", json=replacement, headers=as_flow_manager)
    assert changed.status_code == 200, changed.text
    assert changed.json() == replacement

    new_application = submit(client, as_applicant, room_id=2)
    old_detail = client.get(f"/api/v1/room/applications/{existing['id']}", headers=as_applicant).json()
    assert old_detail["total_levels"] == 2
    assert new_application["total_levels"] == 1

    settings = {
        "max_violations": 2,
        "violation_window_days": 14,
        "advance_days_min": 1,
        "advance_days_max": 20,
    }
    updated = client.put("/api/v1/room/settings", json=settings, headers=as_flow_manager)
    assert updated.status_code == 200
    assert client.get("/api/v1/room/settings", headers=as_applicant).json() == settings
