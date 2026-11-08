"""提交申请：时间、教室、资格与冲突规则，快照与通知。"""

from datetime import timedelta

import pytest
from app import room_service
from app.models import Application, Setting
from campus_common.testing import NOW
from sqlalchemy import update

from tests.conftest import APPLICANT, ROOM, body, headers, m1_room, notifications, slot

pytestmark = pytest.mark.db

ALL_DAY = [{"weekday": day, "open_hour": 0, "close_hour": 24} for day in range(7)]


def post(client, as_user, **overrides):
    return client.post("/api/v1/room/applications", json=body(**overrides), headers=as_user)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def test_submit_snapshots_flow_applicant_and_room_and_notifies_level_one(client, db, as_applicant, m1_calls):
    response = post(client, as_applicant)
    assert response.status_code == 201, response.text
    created = response.json()
    assert (created["status"], created["current_level"], created["total_levels"]) == ("pending", 1, 2)
    assert created["applicant"] == {
        "id": APPLICANT,
        "username": "u1001",
        "name": "测试用户1001",
        "dept_id": 1,
    }
    assert created["deadline_at"] == (NOW + timedelta(hours=48)).isoformat()

    stored = db.get(Application, created["id"])
    assert [(lv["scope"], lv["approver_perm"]) for lv in stored.flow_snapshot] == [
        ("dept", "room:approve"),
        ("school", "room:approve_school"),
    ]
    [notice] = notifications(db, "room.application_submitted")
    assert (notice["user_ids"], notice["perm"], notice["dept_id"]) == ([], "room:approve", 1)
    assert notice["params"] == {
        "application_id": created["id"],
        "room": "第三教学楼 H3106",
        "purpose": "班级读书会",
        **slot(),
        "applicant": "测试用户1001",
        "attendees": 30,
        "level": 1,
    }
    # 只查询了违约次数和教室，没有调用 common
    assert [(method, path) for method, path, _ in m1_calls] == [
        ("GET", f"/internal/v1/users/{APPLICANT}/violations"),
        ("GET", "/internal/v1/rooms/1"),
    ]


def test_purpose_is_stripped_and_must_not_be_blank(client, db, as_applicant, m1_calls):
    assert post(client, as_applicant, purpose="   ").status_code == 422
    assert post(client, as_applicant, purpose="  读书会  ").json()["purpose"] == "读书会"


def test_overlap_rejected_but_adjacent_slot_allowed(client, db, as_applicant, m1_calls):
    assert post(client, as_applicant).status_code == 201
    assert error(post(client, as_applicant, **slot(2, 15, 17))) == (409, "APPLICATION_TIME_CONFLICT")
    assert post(client, as_applicant, **slot(2, 16, 18)).status_code == 201
    assert post(client, as_applicant, **slot(2, 12, 14)).status_code == 201


def test_exclusion_constraint_rejects_overlap_when_precheck_misses_it(
    client, db, as_applicant, m1_calls, monkeypatch
):
    """模拟并发提交：两个请求的预检查都没看到对方，由排除约束拒绝后到的一方。"""
    assert post(client, as_applicant).status_code == 201
    monkeypatch.setattr(room_service, "ACTIVE_STATUSES", ())
    assert error(post(client, as_applicant, **slot(2, 15, 17))) == (409, "APPLICATION_TIME_CONFLICT")
    assert post(client, as_applicant, **slot(2, 16, 18)).status_code == 201


def test_advance_days_count_calendar_days_in_business_time_zone(client, db, as_applicant, monkeypatch):
    """NOW 是北京时间 06:00，UTC 日期还是前一天：按 UTC 算日期会把今天 23 点算成"明天"。"""
    m1_room(monkeypatch, open_hours=ALL_DAY)
    assert error(post(client, as_applicant, **slot(0, 22, 23))) == (400, "ADVANCE_DAYS_OUT_OF_RANGE")
    assert post(client, as_applicant, **slot(1, 0, 1)).status_code == 201
    assert post(client, as_applicant, **slot(30, 22, 23)).status_code == 201
    assert error(post(client, as_applicant, **slot(31, 0, 1))) == (400, "ADVANCE_DAYS_OUT_OF_RANGE")


def test_same_day_application_must_start_after_now(client, db, as_applicant, monkeypatch):
    m1_room(monkeypatch, open_hours=ALL_DAY)
    db.execute(update(Setting).where(Setting.key == "advance_days_min").values(value=0))
    db.commit()
    assert error(post(client, as_applicant, **slot(0, 6, 7))) == (400, "ADVANCE_DAYS_OUT_OF_RANGE")
    late = {"start_at": (NOW + timedelta(seconds=1)).isoformat(), "end_at": slot(0, 6, 7)["end_at"]}
    assert post(client, as_applicant, **late).status_code == 201


def test_slot_must_be_within_open_hours_of_that_weekday(client, db, as_applicant, monkeypatch):
    weekday = (NOW.date() + timedelta(days=2)).weekday()
    m1_room(monkeypatch, open_hours=[{"weekday": weekday, "open_hour": 8, "close_hour": 22}])
    assert error(post(client, as_applicant, **slot(2, 7, 9))) == (400, "OUTSIDE_OPEN_HOURS")
    assert error(post(client, as_applicant, **slot(2, 21, 23))) == (400, "OUTSIDE_OPEN_HOURS")
    assert error(post(client, as_applicant, **slot(3, 10, 12))) == (400, "OUTSIDE_OPEN_HOURS")  # 当天不开放
    assert post(client, as_applicant, **slot(2, 8, 10)).status_code == 201
    assert post(client, as_applicant, **slot(2, 20, 22)).status_code == 201


def test_application_cannot_cross_midnight(client, db, as_applicant, monkeypatch):
    m1_room(monkeypatch, open_hours=ALL_DAY)
    cross = {"start_at": slot(2, 23, 24)["start_at"], "end_at": slot(3, 0, 1)["end_at"]}
    assert error(post(client, as_applicant, **cross)) == (400, "OUTSIDE_OPEN_HOURS")
    assert post(client, as_applicant, **slot(2, 23, 24)).status_code == 201


def test_attendees_up_to_room_capacity(client, db, as_applicant, m1_calls):
    capacity = ROOM["capacity"]
    assert error(post(client, as_applicant, attendees=capacity + 1)) == (400, "ATTENDEES_EXCEED_CAPACITY")
    assert post(client, as_applicant, attendees=capacity).status_code == 201


def test_department_room_only_for_its_department(client, db, monkeypatch):
    m1_room(monkeypatch, dept_id=2)
    other = headers(APPLICANT, ["room:apply"], dept_id=1)
    assert error(post(client, other)) == (403, "DEPT_RESTRICTED")
    assert post(client, headers(1002, ["room:apply"], dept_id=2)).status_code == 201


@pytest.mark.parametrize("changes", [{"is_whole_bookable": False}, {"status": "disabled"}])
def test_room_must_be_enabled_and_whole_bookable(client, db, as_applicant, monkeypatch, changes):
    m1_room(monkeypatch, **changes)
    assert error(post(client, as_applicant)) == (400, "ROOM_NOT_BOOKABLE")


def test_applicant_without_department_cannot_enter_department_level(client, db, m1_calls):
    no_dept = headers(1003, ["room:apply"], dept_id=None)
    assert error(post(client, no_dept)) == (400, "APPLICANT_DEPT_REQUIRED")


def test_ineligible_applicant_gets_reasons(client, db, as_applicant, monkeypatch):
    m1_room(monkeypatch, count=3)
    response = post(client, as_applicant)
    assert error(response) == (403, "NOT_ELIGIBLE")
    assert response.json()["details"] == ["近 30 天违约 3 次，违约达到 3 次不能申请"]


def test_submit_requires_apply_permission(client, db, as_dept_approver, m1_calls):
    assert post(client, as_dept_approver).status_code == 403


def test_end_must_be_after_start(client, db, as_applicant, m1_calls):
    assert post(client, as_applicant, **slot(2, 16, 14)).status_code == 422
