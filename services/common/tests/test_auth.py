"""登录、token 内容、按权限查用户。"""

import pytest
from app.config import settings
from app.models import User
from campus_common.auth import decode_token
from campus_common.testing import service_headers
from sqlalchemy import update

from tests.conftest import M2_KEY

pytestmark = pytest.mark.db


def login(client, username, password="campus123"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_returns_token_with_role_permissions(client, db):
    resp = login(client, "student")
    assert resp.status_code == 200
    user = decode_token(resp.json()["access_token"], settings)
    assert user.username == "student"
    assert user.dept_id == 1
    assert set(user.perms) == {"seat:reserve", "room:apply", "repair:report"}


def test_wrong_password_rejected(client, db):
    resp = login(client, "student", "wrong-password")
    assert resp.status_code == 401
    assert resp.json()["code"] == "LOGIN_FAILED"


def test_me_reflects_token(client, db):
    token = login(client, "worker").json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["perms"] == ["repair:work"]


def test_tampered_token_rejected(client, db):
    token = login(client, "student").json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


def test_users_with_perm_filters_by_dept(client, db):
    headers = service_headers("m2-room", M2_KEY)
    all_approvers = client.get("/internal/v1/users?perm=room:approve", headers=headers).json()
    dept1 = client.get("/internal/v1/users?perm=room:approve&dept_id=1", headers=headers).json()
    assert {u["username"] for u in all_approvers} == {"dept_approver", "school_approver", "admin"}
    assert [u["username"] for u in dept1] == ["dept_approver"]


def test_disabled_user_cannot_log_in(client, db):
    db.execute(update(User).where(User.username == "student").values(active=False))
    db.commit()
    resp = login(client, "student")
    assert resp.status_code == 401
    assert resp.json()["code"] == "LOGIN_FAILED"
