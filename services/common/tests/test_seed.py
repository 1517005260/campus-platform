"""种子数据：不写演示数据的环境（生产）也有可登录的引导管理员；再次运行不改动已存在的账号。"""

import pytest
from app.config import settings
from app.models import User, user_roles
from app.seed import BOOTSTRAP_ADMIN, seed_base
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
