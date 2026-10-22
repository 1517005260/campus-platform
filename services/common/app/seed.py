"""种子数据（幂等，约定见 campus_common.seeding）。

- 基础数据（所有环境）：权限码目录、预置角色及其权限；引导管理员 admin（系统管理员角色，
  密码 ADMIN_PASSWORD），使新环境部署后即可登录并创建其他用户。
  已存在的角色与用户不改动，避免覆盖管理员在线上的调整；新增的权限码和角色会补上。
- 演示数据（SEED_DEMO=true）：院系和除系统管理员外每个预置角色各一个测试账号，密码 DEMO_PASSWORD。
"""

from campus_common.seeding import reset_sequences, run_seed
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.models import Dept, Permission, Role, User, role_permissions, user_roles
from app.permissions import BUILTIN_ROLES, PERMISSIONS
from app.security import hash_password

DEMO_DEPTS = [(1, "计算与智能创新学院"), (2, "数学科学学院")]
DEMO_USERS = [
    # id, username, name, dept_id, roles
    (1, "student", "演示学生", 1, ["student"]),
    (2, "student2", "演示学生（数学）", 2, ["student"]),
    (3, "teacher", "演示教师", 1, ["teacher"]),
    (4, "room_admin", "教室管理员", None, ["room_admin"]),
    (5, "ops_admin", "运营管理员", None, ["ops_admin"]),
    (6, "dept_approver", "院系审批人", 1, ["dept_approver"]),
    (7, "school_approver", "学校审批人", None, ["school_approver"]),
    (8, "dispatcher", "维修调度员", None, ["repair_dispatcher"]),
    (9, "worker", "维修工", None, ["repair_worker"]),
    (10, "screen", "签到屏", None, ["checkin_screen"]),
]
BOOTSTRAP_ADMIN = (11, "admin", "系统管理员", None, ["sys_admin"])


def seed_base(session) -> None:
    session.execute(
        insert(Permission)
        .values([dict(code=c, module=m, description=d) for c, (m, d) in PERMISSIONS.items()])
        .on_conflict_do_nothing()
    )
    for code, (name, perms) in BUILTIN_ROLES.items():
        inserted = session.execute(
            insert(Role)
            .values(code=code, name=name, builtin=True)
            .on_conflict_do_nothing()
            .returning(Role.code)
        ).first()
        if inserted:
            session.execute(
                insert(role_permissions).values([dict(role_code=code, perm_code=p) for p in perms])
            )
    _insert_users(session, [BOOTSTRAP_ADMIN], hash_password(settings.admin_password))


def _insert_users(session, users, password_hash: str) -> None:
    """按固定 ID 写入用户，角色只随新写入的用户一起写入。

    ID 或用户名已被占用（包括管理员删掉种子账号后新建了同名账号）时跳过该用户，
    不改动已存在账号的角色，管理员对种子账号的降权不会在下次部署时被恢复。
    """
    for uid, username, name, dept_id, roles in users:
        inserted = session.execute(
            insert(User)
            .values(
                id=uid,
                username=username,
                name=name,
                dept_id=dept_id,
                email=f"{username}@campus.local",
                password_hash=password_hash,
            )
            .on_conflict_do_nothing()
            .returning(User.id)
        ).first()
        if inserted:
            session.execute(insert(user_roles).values([dict(user_id=uid, role_code=r) for r in roles]))
    reset_sequences(session, settings.db_schema, ["users"])


def seed_demo(session) -> None:
    session.execute(insert(Dept).values([dict(id=i, name=n) for i, n in DEMO_DEPTS]).on_conflict_do_nothing())
    reset_sequences(session, settings.db_schema, ["depts"])
    _insert_users(session, DEMO_USERS, hash_password(settings.demo_password))


if __name__ == "__main__":
    run_seed(settings, seed_base, seed_demo)
