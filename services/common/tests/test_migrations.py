"""数据迁移 0003：已有环境的预置学校审批人改用 room:approve_school，回滚恢复。"""

import pytest
from alembic import command
from alembic.config import Config
from app.models import Permission, Role, role_permissions
from sqlalchemy import insert, select

pytestmark = pytest.mark.db

CONFIG = Config("alembic.ini")
ROLES = ("school_approver", "dept_approver", "sys_admin", "flow_reviewer")


def _perms(db) -> dict[str, set[str]]:
    """关心的角色各自拥有的 room:approve*。"""
    db.expire_all()
    rows = db.execute(
        select(role_permissions.c.role_code, role_permissions.c.perm_code).where(
            role_permissions.c.role_code.in_(ROLES), role_permissions.c.perm_code.like("room:approve%")
        )
    )
    perms: dict[str, set[str]] = {role: set() for role in ROLES}
    for role, perm in rows:
        perms[role].add(perm)
    return perms


UPGRADED = {
    "school_approver": {"room:approve_school"},
    "dept_approver": {"room:approve"},
    "sys_admin": {"room:approve", "room:approve_school"},
    "flow_reviewer": {"room:approve"},
}
DOWNGRADED = {
    "school_approver": {"room:approve"},
    "dept_approver": {"room:approve"},
    "sys_admin": {"room:approve"},
    "flow_reviewer": {"room:approve"},
}


@pytest.fixture
def before_0003(db):
    """回到 0003 之前（预置角色还是旧权限），加一个持有 room:approve 的自定义角色；测试后回到 head。"""
    command.downgrade(CONFIG, "0002")
    try:
        approve = db.get(Permission, "room:approve")
        db.add(Role(code="flow_reviewer", name="审批流复核", builtin=False, perms=[approve]))
        db.commit()
        yield db
    finally:
        command.upgrade(CONFIG, "head")


def test_upgrade_moves_builtin_school_approver_to_school_permission_and_downgrade_restores(before_0003):
    db = before_0003
    assert _perms(db) == DOWNGRADED
    assert db.get(Permission, "room:approve_school") is None

    command.upgrade(CONFIG, "0003")
    assert _perms(db) == UPGRADED
    assert db.get(Permission, "room:approve_school").module == "m2"

    command.downgrade(CONFIG, "0002")
    assert _perms(db) == DOWNGRADED
    assert db.get(Permission, "room:approve_school") is None


def test_upgrade_tolerates_steps_already_applied(before_0003):
    """权限码已在目录、学校审批人已持有新权限码时（例如手工补过），迁移照常完成。"""
    db = before_0003
    db.add(Permission(code="room:approve_school", module="m2", description="学校级审批整教室申请"))
    db.flush()
    db.execute(insert(role_permissions).values(role_code="school_approver", perm_code="room:approve_school"))
    db.commit()

    command.upgrade(CONFIG, "0003")
    assert _perms(db) == UPGRADED
