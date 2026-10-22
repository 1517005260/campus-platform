"""阶段 0 的桩数据：接口结构与鉴权已就绪，返回假数据。实现接口时逐个替换，最终删除本文件。"""

from app import schemas as s
from app.permissions import BUILTIN_ROLES, PERMISSIONS


def user() -> s.UserAdmin:
    return s.UserAdmin(
        id=1, username="20300001", name="张三", dept_id=1, email=None, active=True, roles=["student"]
    )


def roles() -> list[s.RoleOut]:
    return [s.RoleOut(code=c, name=n, builtin=True, perms=p) for c, (n, p) in BUILTIN_ROLES.items()]


def role(code: str, name: str | None = None, perms: list[str] | None = None) -> s.RoleOut:
    default_name, default_perms = BUILTIN_ROLES.get(code, ("自定义角色", []))
    return s.RoleOut(
        code=code, name=name or default_name, builtin=code in BUILTIN_ROLES, perms=perms or default_perms
    )


def permissions() -> list[s.PermissionOut]:
    return [s.PermissionOut(code=c, module=m, description=d) for c, (m, d) in PERMISSIONS.items()]


def depts() -> list[s.DeptOut]:
    return [s.DeptOut(id=1, name="计算与智能创新学院")]
