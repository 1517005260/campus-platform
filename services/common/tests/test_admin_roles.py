"""角色与权限（REQ-D-02）与院系（REQ-D-04）。"""

import pytest
from app.config import settings
from app.models import AuditLog, Dept, Role
from campus_common.auth import decode_token
from sqlalchemy import select

from tests.conftest import headers_for, login

pytestmark = pytest.mark.db


def new_role(client, headers, **overrides):
    body = {
        "code": "lab_manager",
        "name": "实验室管理员",
        "perms": ["seat:room_manage", "seat:stats"],
    } | overrides
    return client.post("/api/v1/admin/roles", json=body, headers=headers)


def test_new_role_grants_its_permissions_at_next_login(client, db, admin):
    resp = new_role(client, admin)
    assert resp.status_code == 201
    assert resp.json() == {
        "code": "lab_manager", "name": "实验室管理员", "builtin": False,
        "perms": ["seat:room_manage", "seat:stats"], "user_count": 0,
    }  # fmt: skip
    client.put("/api/v1/admin/users/3/roles", json={"role_codes": ["teacher", "lab_manager"]}, headers=admin)
    perms = decode_token(login(client, "teacher").json()["access_token"], settings).perms
    assert {"seat:room_manage", "seat:stats", "room:apply"} <= set(perms)
    log = db.scalar(select(AuditLog).where(AuditLog.action == "role.create", AuditLog.actor_type == "user"))
    assert log.target_id == "lab_manager" and log.after["perms"] == ["seat:room_manage", "seat:stats"]


def test_unknown_permission_rejected(client, db, admin):
    resp = new_role(client, admin, perms=["seat:stats", "seat:fly"])
    assert (resp.status_code, resp.json()["code"], resp.json()["details"]) == (
        400, "UNKNOWN_PERMISSION", {"unknown": ["seat:fly"]}
    )  # fmt: skip
    assert db.get(Role, "lab_manager") is None


def test_duplicate_role_code_rejected(client, db, admin):
    assert new_role(client, admin, code="student").json()["code"] == "ROLE_EXISTS"


def test_list_roles_counts_users_and_puts_builtin_first(client, db, admin):
    roles = client.get("/api/v1/admin/roles", headers=admin).json()
    assert [r["builtin"] for r in roles] == sorted((r["builtin"] for r in roles), reverse=True)
    by_code = {r["code"]: r for r in roles}
    assert by_code["dept_approver"]["user_count"] == 5
    assert by_code["auditor"]["builtin"] is False
    # 账号管理员也能看到角色列表（分配角色时要用），但不能改
    manager = headers_for(40, ["admin:user"])
    assert client.get("/api/v1/admin/roles", headers=manager).status_code == 200
    assert new_role(client, manager).status_code == 403


def test_update_custom_role_name_and_perms(client, db, admin):
    resp = client.patch(
        "/api/v1/admin/roles/auditor", json={"name": "合规审计", "perms": ["audit:read"]}, headers=admin
    )
    assert (resp.json()["name"], resp.json()["perms"], resp.json()["user_count"]) == (
        "合规审计",
        ["audit:read"],
        1,
    )
    log = db.scalar(select(AuditLog).where(AuditLog.action == "role.update"))
    assert log.before == {"name": "审计员", "perms": ["audit:read", "seat:stats"]}


def test_builtin_role_perms_editable_but_name_fixed(client, db, admin):
    ok = client.patch("/api/v1/admin/roles/teacher", json={"perms": ["room:apply"]}, headers=admin)
    assert ok.json()["perms"] == ["room:apply"]
    same_name = client.patch("/api/v1/admin/roles/teacher", json={"name": "教师"}, headers=admin)
    assert same_name.status_code == 200
    renamed = client.patch("/api/v1/admin/roles/teacher", json={"name": "老师"}, headers=admin)
    assert (renamed.status_code, renamed.json()["code"]) == (409, "BUILTIN_ROLE_IMMUTABLE")
    assert db.get(Role, "teacher").name == "教师"


@pytest.mark.parametrize(
    ("perms", "ok"),
    [(["admin:user", "admin:role"], True), (["admin:user"], False), (["admin:role", "audit:read"], False)],
)
def test_sys_admin_keeps_admin_permissions(client, db, admin, perms, ok):
    resp = client.patch("/api/v1/admin/roles/sys_admin", json={"perms": perms}, headers=admin)
    assert resp.status_code == (200 if ok else 409)


def test_delete_custom_role_only_when_unused(client, db, admin):
    in_use = client.delete("/api/v1/admin/roles/auditor", headers=admin)
    assert (in_use.status_code, in_use.json()["code"]) == (409, "ROLE_IN_USE")
    client.put("/api/v1/admin/users/39/roles", json={"role_codes": ["ops_admin"]}, headers=admin)
    assert client.delete("/api/v1/admin/roles/auditor", headers=admin).status_code == 204
    assert db.get(Role, "auditor") is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "role.delete")).before["name"] == "审计员"
    assert client.delete("/api/v1/admin/roles/auditor", headers=admin).status_code == 404


def test_builtin_role_cannot_be_deleted_even_when_unused(client, db, admin):
    client.put("/api/v1/admin/users/10/roles", json={"role_codes": []}, headers=admin)
    client.put("/api/v1/admin/users/38/roles", json={"role_codes": []}, headers=admin)
    resp = client.delete("/api/v1/admin/roles/checkin_screen", headers=admin)
    assert (resp.status_code, resp.json()["code"]) == (409, "BUILTIN_ROLE_IMMUTABLE")


def test_permission_catalog_sorted_by_module(client, db, admin):
    perms = client.get("/api/v1/admin/permissions", headers=admin).json()
    keys = [(p["module"], p["code"]) for p in perms]
    assert keys == sorted(keys) and ("common", "audit:read") in keys


# ---------------- 院系 ----------------


def test_create_and_rename_dept(client, db, admin):
    created = client.post("/api/v1/admin/depts", json={"name": " 历史学系 "}, headers=admin)
    assert created.status_code == 201 and created.json()["name"] == "历史学系"
    dept_id = created.json()["id"]
    assert dept_id == 9  # 序列已推到演示院系之后
    renamed = client.patch(f"/api/v1/admin/depts/{dept_id}", json={"name": "历史学系（新）"}, headers=admin)
    assert renamed.json() == {"id": dept_id, "name": "历史学系（新）"}
    actions = db.scalars(
        select(AuditLog.action).where(AuditLog.target_type == "dept", AuditLog.actor_type == "user")
    )
    assert list(actions) == ["dept.create", "dept.update"]
    listed = client.get("/api/v1/admin/depts", headers=headers_for(4, ["seat:room_manage"])).json()
    assert listed[-1] == {"id": dept_id, "name": "历史学系（新）"} and [d["id"] for d in listed] == sorted(
        d["id"] for d in listed
    )


def test_dept_name_unique(client, db, admin):
    assert (
        client.post("/api/v1/admin/depts", json={"name": "物理学系"}, headers=admin).json()["code"]
        == "DEPT_EXISTS"
    )
    resp = client.patch("/api/v1/admin/depts/1", json={"name": "物理学系"}, headers=admin)
    assert (resp.status_code, resp.json()["code"]) == (409, "DEPT_EXISTS")
    assert db.get(Dept, 1).name == "计算与智能创新学院"
    assert client.patch("/api/v1/admin/depts/99", json={"name": "x"}, headers=admin).status_code == 404


def test_dept_maintenance_requires_admin_user(client, db):
    approver = headers_for(6, ["room:approve"])
    assert client.get("/api/v1/admin/depts", headers=approver).status_code == 200
    assert client.post("/api/v1/admin/depts", json={"name": "x"}, headers=approver).status_code == 403


# ---------------- 不越权（只持有 admin:role 的角色管理员） ----------------

ROLE_ADMIN = headers_for(50, ["admin:role", "seat:stats", "audit:read"])


def test_role_admin_cannot_add_permissions_they_lack(client, db):
    resp = client.patch(
        "/api/v1/admin/roles/auditor", json={"perms": ["audit:read", "admin:user"]}, headers=ROLE_ADMIN
    )
    assert (resp.status_code, resp.json()["code"], resp.json()["details"]) == (
        403, "PERMISSION_ESCALATION", {"excess": ["admin:user"]}
    )  # fmt: skip
    assert sorted(p.code for p in db.get(Role, "auditor").perms) == ["audit:read", "seat:stats"]


def test_role_admin_cannot_create_role_with_permissions_they_lack(client, db):
    resp = new_role(client, ROLE_ADMIN, perms=["seat:stats", "seat:config"])
    assert (resp.status_code, resp.json()["details"]) == (403, {"excess": ["seat:config"]})
    assert new_role(client, ROLE_ADMIN, perms=["seat:stats"]).status_code == 201


def test_role_admin_cannot_remove_permissions_they_lack(client, db):
    # teacher 有 room:apply、repair:report，角色管理员没有，不能动它们
    resp = client.patch("/api/v1/admin/roles/teacher", json={"perms": ["room:apply"]}, headers=ROLE_ADMIN)
    assert resp.json()["details"] == {"excess": ["repair:report"]}
    # 只增删自己拥有的权限码可以，其他权限码保持不变
    ok = client.patch(
        "/api/v1/admin/roles/teacher",
        json={"perms": ["room:apply", "repair:report", "seat:stats"]},
        headers=ROLE_ADMIN,
    )
    assert ok.status_code == 200
    # 改名不涉及权限码
    assert (
        client.patch("/api/v1/admin/roles/auditor", json={"name": "审计"}, headers=ROLE_ADMIN).status_code
        == 200
    )


def test_role_admin_cannot_delete_role_with_permissions_they_lack(client, db, admin):
    new_role(client, admin, code="ops_helper", perms=["seat:config"])
    resp = client.delete("/api/v1/admin/roles/ops_helper", headers=ROLE_ADMIN)
    assert resp.json()["code"] == "PERMISSION_ESCALATION"
    assert client.delete("/api/v1/admin/roles/ops_helper", headers=admin).status_code == 204
