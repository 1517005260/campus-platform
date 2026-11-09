"""定时任务：超时撤销与残留占用释放。时刻作为参数传入。"""

from datetime import timedelta

import pytest
from app import clients, jobs
from app.jobs import expire_overdue, release_leftover_blocks
from app.models import Application, ApprovalRecord
from app.room_service import RELEASE_GRACE
from campus_common.errors import AppError
from campus_common.testing import NOW, record_service_calls
from sqlalchemy import func, select

from tests.conftest import APPLICANT, notifications, slot
from tests.test_approval import act, set_columns, stored, submit

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("m1_calls")]


def expire_records(db, application_id: int) -> list[tuple[int, str | None]]:
    return db.execute(
        select(ApprovalRecord.level, ApprovalRecord.comment).where(
            ApprovalRecord.application_id == application_id, ApprovalRecord.action == "expire"
        )
    ).all()


def test_expire_at_deadline_inclusive_and_only_once(client, db, as_applicant):
    application_id = submit(client, as_applicant)
    deadline = stored(db, application_id).deadline_at

    assert expire_overdue(db, deadline - timedelta(microseconds=1)) == []
    assert expire_overdue(db, deadline) == [application_id]
    db.commit()
    assert expire_overdue(db, deadline + timedelta(minutes=1)) == []
    db.commit()

    assert stored(db, application_id).status == "expired"
    assert expire_records(db, application_id) == [(1, "当前级别审批超时")]
    [notice] = notifications(db, "room.application_expired")
    assert notice["user_ids"] == [APPLICANT]
    assert (notice["params"]["level"], notice["params"]["cause"]) == (1, "deadline")


def test_expire_when_slot_starts_before_deadline(client, db, as_applicant, as_dept_approver):
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    start = NOW + timedelta(hours=10)  # 早于第 2 级截止时间 NOW + 48h
    set_columns(db, application_id, start_at=start, end_at=start + timedelta(hours=1))

    assert expire_overdue(db, start - timedelta(microseconds=1)) == []
    assert expire_overdue(db, start) == [application_id]
    db.commit()
    assert expire_records(db, application_id) == [(2, "申请时段已开始，审批未完成")]
    [notice] = notifications(db, "room.application_expired")
    assert (notice["params"]["level"], notice["params"]["cause"]) == (2, "started")


def test_expire_waits_while_occupy_may_be_in_flight(client, db, as_applicant, as_dept_approver):
    """最终审批在截止时刻请求了 M1 占用（结果未知）：RELEASE_GRACE 内不撤销，之后撤销。"""
    application_id = submit(client, as_applicant)
    act(client, application_id, "approve", as_dept_approver)
    deadline = stored(db, application_id).deadline_at
    set_columns(db, application_id, occupy_requested_at=deadline)

    assert expire_overdue(db, deadline + RELEASE_GRACE - timedelta(microseconds=1)) == []
    assert expire_overdue(db, deadline + RELEASE_GRACE) == [application_id]


def test_expire_skips_applications_no_longer_pending(client, db, as_applicant, as_dept_approver):
    application_id = submit(client, as_applicant)
    act(client, application_id, "reject", as_dept_approver)
    assert expire_overdue(db, NOW + timedelta(days=30)) == []


def ended_after_occupy_attempt(client, db, as_applicant, as_dept_approver, status: str) -> int:
    """最终审批请求过 M1 占用（结果未知），之后申请以 status 结束。"""
    application_id = submit(client, as_applicant)
    set_columns(db, application_id, occupy_requested_at=NOW, status=status)
    return application_id


@pytest.mark.parametrize("status", ["rejected", "withdrawn", "expired"])
def test_leftover_block_released_after_grace_once(
    client, db, as_applicant, as_dept_approver, monkeypatch, status
):
    application_id = ended_after_occupy_attempt(client, db, as_applicant, as_dept_approver, status)
    calls = record_service_calls(monkeypatch, clients.m1, {"released": True})

    assert release_leftover_blocks(db, NOW + RELEASE_GRACE - timedelta(microseconds=1)) == []
    assert calls == []
    assert release_leftover_blocks(db, NOW + RELEASE_GRACE) == [application_id]
    db.commit()
    assert [(m, p) for m, p, _ in calls] == [("DELETE", f"/internal/v1/blocks/M2_OCCUPY/{application_id}")]
    assert stored(db, application_id).occupy_requested_at is None
    assert release_leftover_blocks(db, NOW + timedelta(hours=1)) == []
    assert len(calls) == 1


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_block_kept_while_pending_or_approved(
    client, db, as_applicant, as_dept_approver, monkeypatch, status
):
    ended_after_occupy_attempt(client, db, as_applicant, as_dept_approver, status)
    calls = record_service_calls(monkeypatch, clients.m1, {"released": True})
    assert release_leftover_blocks(db, NOW + timedelta(hours=1)) == []
    assert calls == []


def test_leftover_release_retried_after_grace_when_m1_fails(
    client, db, as_applicant, as_dept_approver, monkeypatch
):
    application_id = ended_after_occupy_attempt(client, db, as_applicant, as_dept_approver, "expired")
    calls = record_service_calls(monkeypatch, clients.m1, {"released": True})
    real_request = clients.m1._http.request

    async def unavailable(*args, **kwargs):
        raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")

    monkeypatch.setattr(clients.m1._http, "request", unavailable)
    failed_at = NOW + timedelta(hours=1)
    assert release_leftover_blocks(db, failed_at) == []
    db.commit()
    assert stored(db, application_id).occupy_requested_at == failed_at
    assert db.scalar(select(func.count()).select_from(Application)) == 1

    monkeypatch.setattr(clients.m1._http, "request", real_request)
    assert release_leftover_blocks(db, failed_at + RELEASE_GRACE - timedelta(microseconds=1)) == []
    assert calls == []
    assert release_leftover_blocks(db, failed_at + RELEASE_GRACE) == [application_id]
    assert len(calls) == 1


def test_persistently_failing_release_does_not_starve_later_ones(
    client, db, as_applicant, as_dept_approver, monkeypatch
):
    failing = ended_after_occupy_attempt(client, db, as_applicant, as_dept_approver, "expired")
    later = submit(client, as_applicant, **slot(3))
    set_columns(db, later, occupy_requested_at=NOW + timedelta(seconds=1), status="rejected")
    monkeypatch.setattr(jobs, "RELEASE_BATCH", 1)
    attempts = []

    async def release(application_id):
        attempts.append(application_id)
        if application_id == failing:
            raise AppError(502, "UPSTREAM_UNAVAILABLE", "M1 不可用")
        return True

    monkeypatch.setattr(clients, "release_room", release)
    at = NOW + timedelta(hours=1)
    assert release_leftover_blocks(db, at) == []
    db.commit()
    assert release_leftover_blocks(db, at) == [later]
    db.commit()
    assert attempts == [failing, later]
