"""最终审批本地提交冲突后的 M1 补偿规则。"""

from datetime import timedelta

import pytest
from app import clients, room_service
from app.models import Application
from app.schemas import ApprovalAction
from campus_common.auth import CurrentUser
from campus_common.clients.m1 import M1BlockResult
from campus_common.errors import AppError
from campus_common.timeutil import now
from sqlalchemy.orm.exc import StaleDataError


class ConflictingSession:
    def __init__(self, fresh_status: str):
        self.fresh = Application(
            id=42,
            applicant_id=1001,
            applicant_dept_id=1,
            room_id=1,
            start_at=now() + timedelta(days=2),
            end_at=now() + timedelta(days=2, hours=2),
            purpose="读书会",
            attendees=20,
            status=fresh_status,
            flow_snapshot=[
                {
                    "level": 1,
                    "approver_perm": "room:approve",
                    "scope": "school",
                    "timeout_hours": 48,
                }
            ],
            current_level=1,
            deadline_at=now() + timedelta(hours=48),
            version=2,
        )
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        raise StaleDataError()

    async def rollback(self):
        return None

    async def get(self, model, id_, **kwargs):
        return self.fresh


def pending_application() -> Application:
    return Application(
        id=42,
        applicant_id=1001,
        applicant_dept_id=1,
        room_id=1,
        start_at=now() + timedelta(days=2),
        end_at=now() + timedelta(days=2, hours=2),
        purpose="读书会",
        attendees=20,
        status="pending",
        flow_snapshot=[
            {
                "level": 1,
                "approver_perm": "room:approve",
                "scope": "school",
                "timeout_hours": 48,
            }
        ],
        current_level=1,
        deadline_at=now() + timedelta(hours=48),
        version=1,
    )


@pytest.mark.parametrize(
    ("fresh_status", "expected_releases"),
    [("expired", [42]), ("approved", [])],
)
async def test_final_approval_compensates_only_when_other_operation_did_not_approve(
    monkeypatch, fresh_status, expected_releases
):
    session = ConflictingSession(fresh_status)
    application = pending_application()
    approver = CurrentUser(
        id=2001,
        username="approver",
        name="审批人",
        dept_id=1,
        roles=["approver"],
        perms=["room:approve"],
    )
    releases = []

    async def get_application(_session, _application_id):
        return application

    async def occupy(*args, **kwargs):
        return M1BlockResult(block_id=9, cancelled_reservations=[])

    async def release(application_id):
        releases.append(application_id)
        return True

    monkeypatch.setattr(room_service, "get_application", get_application)
    monkeypatch.setattr(clients, "occupy_room", occupy)
    monkeypatch.setattr(clients, "release_room", release)

    with pytest.raises(AppError) as caught:
        await room_service.approve(session, approver, 42, ApprovalAction())

    assert caught.value.code == "APPLICATION_STATE_CONFLICT"
    assert releases == expected_releases
