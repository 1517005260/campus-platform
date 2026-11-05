"""种子数据：不写演示数据的环境（生产）也有可登录的引导管理员；再次运行不改动已存在的账号。"""

import pytest
from app.config import settings
from app.models import AuditLog, Dept, Notification, Role, User, role_permissions, user_roles
from app.seed import BOOTSTRAP_ADMIN, DEMO_USERS, seed_base, seed_demo
from campus_common.auth import decode_token
from sqlalchemy import delete, func, select

pytestmark = pytest.mark.db


@pytest.fixture
def db_seed():
    return seed_base  # 只写基础数据，与 SEED_DEMO=false 的环境一致


def test_bootstrap_admin_can_log_in_without_demo_data(client, db):
    assert db.scalar(select(func.count()).select_from(User)) == 1
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": settings.admin_password})
    assert resp.status_code == 200
    assert "admin:user" in decode_token(resp.json()["access_token"], settings).perms


def test_seed_base_keeps_existing_admin_password(client, db, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "changed-later")
    seed_base(db)
    db.commit()
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changed-later"})
    assert resp.status_code == 401


def test_seed_base_keeps_admin_role_changes(db):
    db.execute(delete(user_roles).where(user_roles.c.user_id == BOOTSTRAP_ADMIN[0]))
    db.commit()
    seed_base(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(user_roles)) == 0


def test_seed_base_skips_admin_when_username_taken_by_another_account(db):
    db.execute(delete(user_roles))
    db.execute(delete(User))
    db.add(User(id=50, username="admin", name="新建的同名账号", email="admin@example.edu", password_hash="x"))
    db.commit()
    seed_base(db)
    db.commit()
    assert db.scalars(select(User.id)).all() == [50]
    assert db.scalar(select(func.count()).select_from(user_roles)) == 0


# ---------------- 演示数据 ----------------


def seed_all(session) -> None:
    seed_base(session)
    seed_demo(session)


def table_counts(db) -> dict[str, int]:
    tables = [User, Dept, Role, Notification, AuditLog]
    return {t.__tablename__: db.scalar(select(func.count()).select_from(t)) for t in tables} | {
        "user_roles": db.scalar(select(func.count()).select_from(user_roles))
    }


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_seed_is_idempotent(client, db):
    before = table_counts(db)
    seed_all(db)
    db.commit()
    assert table_counts(db) == before
    assert before["users"] == len(DEMO_USERS) + 1


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_accounts_log_in_with_demo_password_except_disabled(client, db):
    for u in DEMO_USERS:
        resp = client.post(
            "/api/v1/auth/login", json={"username": u.username, "password": settings.demo_password}
        )
        assert resp.status_code == (200 if u.active else 401), u.username


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_ids_referenced_by_other_services_are_stable(db):
    users = dict(db.execute(select(User.id, User.username).where(User.id <= 11)).all())
    assert users == {
        1: "student", 2: "student2", 3: "teacher", 4: "room_admin", 5: "ops_admin", 6: "dept_approver",
        7: "school_approver", 8: "dispatcher", 9: "worker", 10: "screen", 11: "admin",
    }  # fmt: skip
    assert db.get(Dept, 1).name == "计算与智能创新学院" and db.get(Dept, 2).name == "数学科学学院"


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_emails_are_not_deliverable(db):
    assert {e.split("@")[1] for e in db.scalars(select(User.email))} == {"campus.local"}


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_seed_keeps_admin_changes_to_custom_roles(db):
    db.execute(delete(role_permissions).where(role_permissions.c.role_code == "auditor"))
    db.commit()
    seed_demo(db)
    db.commit()
    assert db.get(Role, "auditor").perms == []


@pytest.mark.parametrize("db_seed", [seed_all])
def test_demo_seed_records_what_it_created(db):
    rows = db.execute(select(AuditLog.action, AuditLog.target_id).where(AuditLog.actor_id == "seed")).all()
    assert {t for a, t in rows if a == "role.create"} == {"auditor", "user_manager"}
    assert {int(t) for a, t in rows if a == "user.create"} == {u.id for u in DEMO_USERS}
    assert len([1 for a, _ in rows if a == "dept.create"]) == 8


@pytest.mark.parametrize("db_seed", [seed_all])
def test_welcome_notification_only_for_active_demo_accounts(db):
    welcomed = set(db.scalars(select(Notification.user_id).where(Notification.template == "common.welcome")))
    assert welcomed == {u.id for u in DEMO_USERS if u.active}
    assert 26 not in welcomed  # 已停用的演示账号
