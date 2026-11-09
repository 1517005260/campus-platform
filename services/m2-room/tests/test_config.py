"""资格门槛、审批流与参数配置。"""

from datetime import datetime, timedelta

import pytest
from app import clients
from app.models import Setting
from campus_common.testing import NOW, record_service_calls
from sqlalchemy import update

from tests.conftest import APPLICANT, headers, slot
from tests.test_approval import submit

pytestmark = pytest.mark.db

LEVEL = {"level": 1, "approver_perm": "room:approve_school", "scope": "school", "timeout_hours": 24}
FLOW = {"name": "单级审批", "room_type": None, "dept_scoped": None, "priority": 10, "levels": [LEVEL]}


def eligibility(client, as_applicant, monkeypatch, count: int):
    calls = record_service_calls(monkeypatch, clients.m1, {"count": count})
    return client.get("/api/v1/room/eligibility", headers=as_applicant).json(), calls


def test_eligibility_boundary_and_reason_states_actual_and_limit(client, db, as_applicant, monkeypatch):
    allowed, calls = eligibility(client, as_applicant, monkeypatch, 2)
    assert allowed == {"eligible": True, "reasons": []}
    (method, path, kwargs) = calls[0]
    assert (method, path) == ("GET", f"/internal/v1/users/{APPLICANT}/violations")
    assert datetime.fromisoformat(kwargs["params"]["since"]) == NOW - timedelta(days=30)

    blocked, _ = eligibility(client, as_applicant, monkeypatch, 3)
    assert blocked == {"eligible": False, "reasons": ["近 30 天违约 3 次，违约达到 3 次不能申请"]}


def test_eligibility_uses_adjusted_limit(client, db, as_applicant, monkeypatch):
    db.execute(update(Setting).where(Setting.key == "max_violations").values(value=2))
    db.commit()
    assert eligibility(client, as_applicant, monkeypatch, 2)[0]["eligible"] is False


def test_flow_changes_only_affect_new_applications(client, db, as_applicant, as_flow_manager, m1_calls):
    existing = submit(client, as_applicant)
    changed = client.put("/api/v1/room/flows", json=[FLOW | {"name": "  单级审批 "}], headers=as_flow_manager)
    assert changed.status_code == 200, changed.text
    assert changed.json() == [FLOW]

    new = submit(client, as_applicant, **slot(3))

    def total_levels(application_id):
        return client.get(f"/api/v1/room/applications/{application_id}", headers=as_applicant).json()[
            "total_levels"
        ]

    assert (total_levels(existing), total_levels(new)) == (2, 1)


@pytest.mark.parametrize(
    "flows",
    [
        [],
        [FLOW | {"name": "   "}],
        [FLOW | {"name": "x" * 51}],
        [FLOW | {"levels": []}],
        [FLOW | {"levels": [LEVEL | {"approver_perm": "room:approve"}]}],  # 学校级须用 room:approve_school
        [FLOW | {"levels": [LEVEL | {"scope": "dept"}]}],  # 院系级须用 room:approve
        [FLOW | {"levels": [LEVEL | {"approver_perm": "seat:reserve"}]}],
        [FLOW | {"levels": [LEVEL | {"level": 2}]}],
    ],
)
def test_invalid_flows_rejected_with_422_and_kept(client, db, as_flow_manager, flows):
    before = client.get("/api/v1/room/flows", headers=as_flow_manager).json()
    assert client.put("/api/v1/room/flows", json=flows, headers=as_flow_manager).status_code == 422
    assert client.get("/api/v1/room/flows", headers=as_flow_manager).json() == before


def test_name_of_maximum_length_accepted_and_duplicates_rejected(client, db, as_flow_manager):
    long_name = [FLOW | {"name": "x" * 50}]
    assert client.put("/api/v1/room/flows", json=long_name, headers=as_flow_manager).status_code == 200
    duplicate = client.put(
        "/api/v1/room/flows", json=[FLOW, FLOW | {"name": " 单级审批"}], headers=as_flow_manager
    )
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "DUPLICATE_FLOW_NAME")
    assert client.get("/api/v1/room/flows", headers=as_flow_manager).json() == long_name


def test_settings_persist_and_invalid_window_rejected(client, db, as_applicant, as_flow_manager):
    settings = {
        "max_violations": 2,
        "violation_window_days": 14,
        "advance_days_min": 3,
        "advance_days_max": 3,
    }
    assert client.put("/api/v1/room/settings", json=settings, headers=as_flow_manager).status_code == 200
    invalid = settings | {"advance_days_max": 2}
    assert client.put("/api/v1/room/settings", json=invalid, headers=as_flow_manager).status_code == 422
    assert client.get("/api/v1/room/settings", headers=as_applicant).json() == settings


def test_configuration_requires_flow_manage(client, db, as_applicant):
    assert client.put("/api/v1/room/flows", json=[FLOW], headers=as_applicant).status_code == 403
    assert client.get("/api/v1/room/flows", headers=headers(2001, ["room:approve"])).status_code == 403
