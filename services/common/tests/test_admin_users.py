"""用户管理（REQ-D-03）：新建、查询、修改、停用/启用、设置角色、越权与自锁保护。"""

import pytest
from app.config import settings
from app.models import AuditLog, Notification, User
from app.security import verify_password
from campus_common.auth import decode_token
from campus_common.testing import service_headers
from sqlalchemy import select

from tests.conftest import M2_KEY, headers_for, login

pytestmark = pytest.mark.db

NEW_USER = {
    "username": "23300240099",
    "name": "新同学",
    "dept_id": 1,
    "password": "pass-1234",
    "role_codes": ["student"],
}


def create(client, headers, **overrides):
    return client.post("/api/v1/admin/users", json=NEW_USER | overrides, headers=headers)


def test_created_user_can_log_in_with_role_permissions(client, db, admin):
    resp = create(client, admin)
    assert resp.status_code == 201
    body = resp.json()
    assert body["roles"] == ["student"] and body["active"] is True and "password_hash" not in body
    stored = db.scalar(select(User).where(User.username == NEW_USER["username"]))
    assert stored.password_hash != NEW_USER["password"] and verify_password("pass-1234", stored.password_hash)

    token = login(client, NEW_USER["username"], "pass-1234").json()["access_token"]
    me = decode_token(token, settings)
    assert (me.dept_id, set(me.perms)) == (1, {"seat:reserve", "room:apply", "repair:report"})


def test_create_writes_audit_without_password(client, db, admin):
    user_id = create(client, admin).json()["id"]
    log = db.scalar(
        select(AuditLog).where(AuditLog.action == "user.create", AuditLog.target_id == str(user_id))
    )
    assert (log.actor_type, log.actor_id, log.module) == ("user", "11", "common")
    assert "password" not in str(log.after) and log.after["roles"] == ["student"]


def test_duplicate_username_rejected(client, db, admin):
    resp = create(client, admin, username="student")
    assert (resp.status_code, resp.json()["code"]) == (409, "USERNAME_EXISTS")


@pytest.mark.parametrize(
    ("overrides", "code"),
    [({"dept_id": 999}, "DEPT_NOT_FOUND"), ({"role_codes": ["student", "no_such_role"]}, "UNKNOWN_ROLE")],
)
def test_create_rejects_unknown_references(client, db, admin, overrides, code):
    resp = create(client, admin, **overrides)
    assert (resp.status_code, resp.json()["code"]) == (400, code)
    assert db.scalar(select(User).where(User.username == NEW_USER["username"])) is None


@pytest.mark.parametrize(
    ("overrides", "ok"),
    [
        ({"password": "1234567"}, False),
        ({"password": "12345678"}, True),
        ({"username": "a b"}, False),
        ({"name": "  "}, False),
    ],
)
def test_create_validates_fields(client, db, admin, overrides, ok):
    assert create(client, admin, **overrides).status_code == (201 if ok else 422)


def test_list_filters_and_paginates(client, db, admin):
    by_dept = client.get("/api/v1/admin/users?dept_id=2&role=student", headers=admin).json()
    assert {u["username"] for u in by_dept["items"]} == {"student2", "22300180015", "23300180032"}

    by_keyword = client.get("/api/v1/admin/users", params={"keyword": "APPROVER_"}, headers=admin).json()
    assert {u["username"] for u in by_keyword["items"]} == {
        "approver_math", "approver_phys", "approver_econ", "approver_mgmt"
    }  # fmt: skip

    disabled = client.get("/api/v1/admin/users?active=false", headers=admin).json()
    assert [u["username"] for u in disabled["items"]] == ["20300240003"]

    page1 = client.get("/api/v1/admin/users?size=5", headers=admin).json()
    page2 = client.get("/api/v1/admin/users?size=5&page=2", headers=admin).json()
    assert page1["total"] == page2["total"] == db.query(User).count()
    assert [u["id"] for u in page1["items"]] == [1, 2, 3, 4, 5]
    assert [u["id"] for u in page2["items"]] == [6, 7, 8, 9, 10]


def test_keyword_treats_wildcards_literally(client, db, admin):
    resp = client.get("/api/v1/admin/users", params={"keyword": "%"}, headers=admin).json()
    assert resp["total"] == 0


def test_disabled_user_cannot_log_in_and_is_hidden_from_other_services(client, db, admin):
    assert login(client, "dept_approver").status_code == 200
    resp = client.patch("/api/v1/admin/users/6", json={"active": False}, headers=admin)
    assert resp.status_code == 200 and resp.json()["active"] is False
    assert login(client, "dept_approver").json()["code"] == "LOGIN_FAILED"
    approvers = client.get(
        "/internal/v1/users?perm=room:approve&dept_id=1", headers=service_headers("m2-room", M2_KEY)
    ).json()
    assert approvers == []

    client.patch("/api/v1/admin/users/6", json={"active": True}, headers=admin)
    assert login(client, "dept_approver").status_code == 200


def test_update_profile_clears_dept_and_resets_password(client, db, admin):
    resp = client.patch(
        "/api/v1/admin/users/1",
        json={"name": "改名学生", "dept_id": None, "password": "new-pass-1"},
        headers=admin,
    )
    assert resp.status_code == 200
    assert (resp.json()["name"], resp.json()["dept_id"], resp.json()["email"]) == (
        "改名学生", None, "student@campus.local"
    )  # fmt: skip
    assert login(client, "student").status_code == 401
    assert login(client, "student", "new-pass-1").status_code == 200
    log = db.scalar(select(AuditLog).where(AuditLog.action == "user.update"))
    assert log.before == {"name": "演示学生", "dept_id": 1}
    assert log.after == {"name": "改名学生", "dept_id": None, "password": "reset"}


def test_update_rejects_unknown_dept_and_user(client, db, admin):
    assert (
        client.patch("/api/v1/admin/users/1", json={"dept_id": 999}, headers=admin).json()["code"]
        == "DEPT_NOT_FOUND"
    )
    assert client.patch("/api/v1/admin/users/999", json={"active": False}, headers=admin).status_code == 404


def test_cannot_disable_self(client, db, admin):
    resp = client.patch("/api/v1/admin/users/11", json={"active": False}, headers=admin)
    assert (resp.status_code, resp.json()["code"]) == (409, "SELF_LOCKOUT")
    assert db.get(User, 11).active is True


def test_set_roles_takes_effect_at_next_login_and_notifies_user(client, db, admin):
    old_token = login(client, "student").json()["access_token"]
    resp = client.put(
        "/api/v1/admin/users/1/roles", json={"role_codes": ["teacher", "auditor"]}, headers=admin
    )
    assert resp.json()["roles"] == ["auditor", "teacher"]

    assert "seat:reserve" in decode_token(old_token, settings).perms  # 旧 token 到期前不变
    new = decode_token(login(client, "student").json()["access_token"], settings)
    assert set(new.perms) == {"room:apply", "repair:report", "audit:read", "seat:stats"}

    note = db.scalar(select(Notification).where(Notification.template == "common.roles_changed"))
    assert note.user_id == 1 and "审计员" in note.content and note.channels == ["inapp"]
    log = db.scalar(select(AuditLog).where(AuditLog.action == "user.set_roles"))
    assert (log.before, log.after) == ({"roles": ["student"]}, {"roles": ["auditor", "teacher"]})


def test_set_same_roles_is_a_no_op(client, db, admin):
    client.put("/api/v1/admin/users/1/roles", json={"role_codes": ["student"]}, headers=admin)
    assert db.scalar(select(Notification).where(Notification.template == "common.roles_changed")) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "user.set_roles")) is None


def test_set_roles_rejects_unknown_role(client, db, admin):
    resp = client.put("/api/v1/admin/users/1/roles", json={"role_codes": ["ghost"]}, headers=admin)
    assert (resp.status_code, resp.json()["code"], resp.json()["details"]) == (
        400,
        "UNKNOWN_ROLE",
        {"unknown": ["ghost"]},
    )


def test_admin_cannot_remove_own_user_management(client, db, admin):
    resp = client.put("/api/v1/admin/users/11/roles", json={"role_codes": ["auditor"]}, headers=admin)
    assert resp.json()["code"] == "SELF_LOCKOUT"
    ok = client.put(
        "/api/v1/admin/users/11/roles", json={"role_codes": ["sys_admin", "auditor"]}, headers=admin
    )
    assert ok.status_code == 200


# 账号管理员（演示角色 user_manager：admin:user 加学生、教师的权限码）


@pytest.fixture
def manager(client, db):
    return {"Authorization": f"Bearer {login(client, 'user_manager').json()['access_token']}"}


def test_user_manager_manages_students_and_teachers(client, db, manager):
    assert create(client, manager, role_codes=["student"]).status_code == 201
    assert (
        client.patch("/api/v1/admin/users/12", json={"password": "reset-123"}, headers=manager).status_code
        == 200
    )
    assert client.patch("/api/v1/admin/users/27", json={"active": False}, headers=manager).status_code == 200
    resp = client.put(
        "/api/v1/admin/users/12/roles", json={"role_codes": ["student", "teacher"]}, headers=manager
    )
    assert resp.status_code == 200


def test_user_manager_cannot_grant_roles_beyond_own_permissions(client, db, manager):
    resp = client.put("/api/v1/admin/users/40/roles", json={"role_codes": ["sys_admin"]}, headers=manager)
    assert (resp.status_code, resp.json()["code"]) == (403, "PERMISSION_ESCALATION")
    assert "admin:role" in resp.json()["details"]["excess"]
    assert create(client, manager, role_codes=["dept_approver"]).json()["code"] == "PERMISSION_ESCALATION"


def test_user_manager_cannot_strip_roles_from_more_privileged_account(client, db, manager):
    resp = client.put("/api/v1/admin/users/11/roles", json={"role_codes": []}, headers=manager)
    assert (resp.status_code, resp.json()["code"]) == (403, "PERMISSION_ESCALATION")
    assert [r.code for r in db.get(User, 11).roles] == ["sys_admin"]


def test_user_manager_cannot_modify_more_privileged_account(client, db, manager):
    resp = client.patch("/api/v1/admin/users/11", json={"password": "taken-over"}, headers=manager)
    assert resp.json()["code"] == "PERMISSION_ESCALATION"
    assert client.patch("/api/v1/admin/users/6", json={"active": False}, headers=manager).status_code == 403
    assert login(client, "admin").status_code == 200


def test_user_endpoints_require_admin_user(client, db):
    student = headers_for(1, ["seat:reserve", "admin:role"])
    assert client.get("/api/v1/admin/users", headers=student).status_code == 403
    assert create(client, student).status_code == 403
