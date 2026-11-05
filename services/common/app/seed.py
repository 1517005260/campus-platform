"""种子数据（幂等，约定见 campus_common.seeding）。

- 基础数据 seed_base：权限码目录、预置角色及其权限；引导管理员 admin（系统管理员角色，密码 ADMIN_PASSWORD），
  使新环境部署后即可登录并创建其他用户。已存在的角色与用户不改动，避免覆盖管理员在线上的调整；
  新增的权限码和角色会补上。
- 演示数据 seed_demo（SEED_DEMO=true，默认开启）：复旦大学的部分院系、各角色的演示账号（密码 DEMO_PASSWORD）、
  两个自定义角色、每个启用的演示账号一条欢迎通知，以及记录这次初始化的审计。全部使用固定 ID，已存在则跳过。

演示账号的邮箱一律是不可投递的 <用户名>@campus.local，生产环境接入真实 SMTP 时提醒也不会发给真实的人。
ID 1–11 的账号与院系 1、2 被其他服务的演示数据和集成测试引用，不要改动它们的 ID 与用户名。
"""

from typing import NamedTuple

from campus_common.seeding import reset_sequences, run_seed
from sqlalchemy.dialects.postgresql import insert

from app import audit
from app.config import settings
from app.models import Dept, Permission, Role, User, role_permissions, user_roles
from app.notification_service import new_notification
from app.permissions import BUILTIN_ROLES, PERMISSIONS
from app.security import hash_password

DEMO_EMAIL_DOMAIN = "campus.local"


class SeedUser(NamedTuple):
    id: int
    username: str
    name: str
    dept_id: int | None
    roles: list[str]
    active: bool = True


# 院系名称取自复旦大学官网"院系设置"（https://www.fudan.edu.cn/594/list.htm）
DEMO_DEPTS = [
    (1, "计算与智能创新学院"),
    (2, "数学科学学院"),
    (3, "物理学系"),
    (4, "经济学院"),
    (5, "管理学院"),
    (6, "新闻学院"),
    (7, "中国语言文学系"),
    (8, "外国语言文学学院"),
]

# 自定义角色（builtin=false），演示"管理员可以新建角色"。
# 账号管理员只能管理权限不超过自己的账号（rbac 的不越权规则），因此带上学生、教师的全部权限码：
# 可以新建、停用、重置学生与教师账号并在两者之间调整角色，不能管理审批人、后勤与管理员账号。
DEMO_ROLES = {
    "auditor": ("审计员", ["audit:read", "seat:stats"]),
    "user_manager": ("账号管理员", ["admin:user", "seat:reserve", "room:apply", "repair:report"]),
}

BOOTSTRAP_ADMIN = SeedUser(11, "admin", "系统管理员", None, ["sys_admin"])

DEMO_USERS = [
    # 1–10：每个预置角色一个，用户名即角色，供文档、集成测试和其他服务的演示数据引用
    SeedUser(1, "student", "演示学生", 1, ["student"]),
    SeedUser(2, "student2", "演示学生（数学）", 2, ["student"]),
    SeedUser(3, "teacher", "演示教师", 1, ["teacher"]),
    SeedUser(4, "room_admin", "教室管理员", None, ["room_admin"]),
    SeedUser(5, "ops_admin", "运营管理员", None, ["ops_admin"]),
    SeedUser(6, "dept_approver", "院系审批人", 1, ["dept_approver"]),
    SeedUser(7, "school_approver", "学校审批人", None, ["school_approver"]),
    SeedUser(8, "dispatcher", "维修调度员", None, ["repair_dispatcher"]),
    SeedUser(9, "worker", "维修工", None, ["repair_worker"]),
    SeedUser(10, "screen", "签到屏", None, ["checkin_screen"]),
    # 12–31：学生，用户名为学号（入学年份 + 院系 + 序号）
    SeedUser(12, "23300240011", "李思远", 1, ["student"]),
    SeedUser(13, "23300240027", "王雨桐", 1, ["student"]),
    SeedUser(14, "24300240008", "陈浩然", 1, ["student"]),
    SeedUser(15, "22300180015", "赵子涵", 2, ["student"]),
    SeedUser(16, "23300180032", "刘嘉怡", 2, ["student"]),
    SeedUser(17, "23300190004", "周博文", 3, ["student"]),
    SeedUser(18, "24300190021", "吴欣然", 3, ["student"]),
    SeedUser(19, "22300680019", "孙一鸣", 4, ["student"]),
    SeedUser(20, "23300680036", "郑可欣", 4, ["student"]),
    SeedUser(21, "23300690012", "黄梓轩", 5, ["student"]),
    SeedUser(22, "24300690045", "林佳琪", 5, ["student"]),
    SeedUser(23, "23300130007", "何俊杰", 6, ["student"]),
    SeedUser(24, "23300100023", "高诗涵", 7, ["student"]),
    SeedUser(25, "24300110016", "马天宇", 8, ["student"]),
    SeedUser(26, "20300240003", "罗晓东", 1, ["student"], active=False),  # 已毕业，账号停用
    # 教师（工号）
    SeedUser(27, "t09021", "张建国", 2, ["teacher"]),
    SeedUser(28, "t11037", "钱丽华", 3, ["teacher"]),
    SeedUser(29, "t12054", "冯志强", 4, ["teacher"]),
    SeedUser(30, "t15008", "许文静", 7, ["teacher"]),
    # 院系审批人（院系 1 已有 dept_approver）
    SeedUser(31, "approver_math", "沈立新", 2, ["dept_approver"]),
    SeedUser(32, "approver_phys", "韩明", 3, ["dept_approver"]),
    SeedUser(33, "approver_econ", "曹雪梅", 4, ["dept_approver"]),
    SeedUser(34, "approver_mgmt", "邓伟", 5, ["dept_approver", "teacher"]),
    # 后勤与运营
    SeedUser(35, "room_admin2", "彭丽", None, ["room_admin"]),
    SeedUser(36, "worker2", "蒋师傅", None, ["repair_worker"]),
    SeedUser(37, "worker3", "杜师傅", None, ["repair_worker"]),
    SeedUser(38, "screen_h3", "签到屏（第三教学楼）", None, ["checkin_screen"]),
    # 自定义角色
    SeedUser(39, "auditor", "叶审计", None, ["auditor"]),
    SeedUser(40, "user_manager", "苏晴", None, ["user_manager"]),
]


def seed_base(session) -> None:
    session.execute(
        insert(Permission)
        .values([dict(code=c, module=m, description=d) for c, (m, d) in PERMISSIONS.items()])
        .on_conflict_do_nothing()
    )
    _insert_roles(session, BUILTIN_ROLES, builtin=True)
    _insert_users(session, [BOOTSTRAP_ADMIN], hash_password(settings.admin_password))


def _insert_roles(session, roles: dict[str, tuple[str, list[str]]], *, builtin: bool) -> list[str]:
    """权限只随新写入的角色一起写入；已存在的角色（含管理员调整过权限的）不改动。返回新写入的角色编码。"""
    inserted = []
    for code, (name, perms) in roles.items():
        if session.execute(
            insert(Role)
            .values(code=code, name=name, builtin=builtin)
            .on_conflict_do_nothing()
            .returning(Role.code)
        ).first():
            session.execute(
                insert(role_permissions).values([dict(role_code=code, perm_code=p) for p in perms])
            )
            inserted.append(code)
    return inserted


def _insert_users(session, users: list[SeedUser], password_hash: str) -> list[SeedUser]:
    """按固定 ID 写入用户，角色只随新写入的用户一起写入。返回新写入的用户。

    ID 或用户名已被占用（包括管理员删掉种子账号后新建了同名账号）时跳过该用户，
    不改动已存在账号的角色，管理员对种子账号的降权不会在下次部署时被恢复。
    """
    inserted = []
    for u in users:
        if session.execute(
            insert(User)
            .values(
                id=u.id,
                username=u.username,
                name=u.name,
                dept_id=u.dept_id,
                email=f"{u.username}@{DEMO_EMAIL_DOMAIN}",
                password_hash=password_hash,
                active=u.active,
            )
            .on_conflict_do_nothing()
            .returning(User.id)
        ).first():
            session.execute(insert(user_roles).values([dict(user_id=u.id, role_code=r) for r in u.roles]))
            inserted.append(u)
    reset_sequences(session, settings.db_schema, ["users"])
    return inserted


def seed_demo(session) -> None:
    depts = session.scalars(
        insert(Dept)
        .values([dict(id=i, name=n) for i, n in DEMO_DEPTS])
        .on_conflict_do_nothing()
        .returning(Dept.id)
    ).all()
    reset_sequences(session, settings.db_schema, ["depts"])
    roles = _insert_roles(session, DEMO_ROLES, builtin=False)
    users = _insert_users(session, DEMO_USERS, hash_password(settings.demo_password))

    # 欢迎通知只发站内信（不触发邮件），只发给新写入且启用的账号
    session.add_all(
        new_notification(
            u.id,
            "common.welcome",
            {"name": u.name},
            channels=["inapp"],
            ref={"module": "common", "type": "user", "id": u.id},
        )
        for u in users
        if u.active
    )
    for dept_id in sorted(depts):
        audit.record(
            session,
            "system",
            "seed",
            "dept.create",
            "dept",
            dept_id,
            after={"name": dict(DEMO_DEPTS)[dept_id]},
        )
    for code in roles:
        name, perms = DEMO_ROLES[code]
        audit.record(
            session,
            "system",
            "seed",
            "role.create",
            "role",
            code,
            after={"name": name, "perms": sorted(perms)},
        )
    for u in users:
        after = {"username": u.username, "roles": sorted(u.roles)}
        audit.record(session, "system", "seed", "user.create", "user", u.id, after=after)


if __name__ == "__main__":
    run_seed(settings, seed_base, seed_demo)
