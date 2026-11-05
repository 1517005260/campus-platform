"""用户、角色、权限、院系管理（REQ-D-02/03/04）。

规则：
- 角色只是权限码的组合；权限码必须存在于目录（permissions 表，由 seed 按 app/permissions.py 写入）。
- 预置角色（builtin）不可删除、不可改名，权限可以调整（新增权限码后由管理员分配给预置角色）；
  系统管理员角色必须保留 admin:user 与 admin:role，避免没有人能再管理用户和角色。
- 自定义角色仍有用户时不可删除，先把用户改到其他角色。
- 不越权（否则 403 PERMISSION_ESCALATION）：操作者只能经手自己拥有的权限码。
  用户：分配的角色、被修改用户现有角色的权限都必须是操作者权限的子集，不能给自己提权或重置更高权限账号的密码；
  角色：新建角色的权限、修改时增加或移除的权限、删除角色的权限都必须是操作者权限的子集，
  只持有 admin:role 的角色管理员不能给角色（包括自己的角色）加上自己没有的权限，也不能拿掉别人的权限。
- 管理员不能停用自己，也不能让自己失去 admin:user（避免把唯一的管理员锁在门外）。
- 院系只能新建和改名，不能删除：M1 教室、M2 审批按院系 ID 引用院系，common 无法确认这些引用已清理。
- 角色、权限与院系的变化写进 token，在用户下次登录后生效（ADR-002，最长为 token 有效期）。
- 每个写操作在同一事务里写一条审计（app/audit.py）。
"""

from campus_common.auth import CurrentUser
from campus_common.db import constraint_errors
from campus_common.errors import AppError, not_found
from campus_common.pagination import Page, PageParams, paginate
from sqlalchemy import Select, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app import schemas as s
from app.models import Dept, Permission, Role, User, user_roles
from app.notification_service import new_notification
from app.security import hash_password_async

SYS_ADMIN_ROLE = "sys_admin"
ADMIN_PERMS = {"admin:user", "admin:role"}

USER_ERRORS = {
    "uq_users_username": (409, "USERNAME_EXISTS", "用户名已存在"),
    "fk_users_dept_id_depts": (400, "DEPT_NOT_FOUND", "院系不存在"),
    "fk_user_roles_role_code_roles": (400, "UNKNOWN_ROLE", "角色不存在"),
}
ROLE_ERRORS = {
    "pk_roles": (409, "ROLE_EXISTS", "角色编码已存在"),
    "fk_role_permissions_perm_code_permissions": (400, "UNKNOWN_PERMISSION", "权限码不存在"),
}
DEPT_ERRORS = {"uq_depts_name": (409, "DEPT_EXISTS", "院系名称已存在")}


# ---------------- 通用规则 ----------------


def perm_holders(perm: str, dept_id: int | None = None) -> Select[tuple[User]]:
    """拥有权限码 perm（可再按院系过滤）的启用用户，按 ID 排序。

    服务间按权限查用户的接口与"按权限码寻址的通知"（NotificationSend.perm）共用这一个查询。"""
    stmt = (
        select(User)
        .join(User.roles)
        .join(Role.perms)
        .where(Permission.code == perm, User.active.is_(True))
        .distinct()
        .order_by(User.id)
    )
    return stmt if dept_id is None else stmt.where(User.dept_id == dept_id)


async def _by_codes[M: (Role, Permission)](
    session: AsyncSession, model: type[M], codes: list[str], error_code: str, what: str
) -> list[M]:
    """按编码取出全部对象（按编码排序）；有不存在的编码时 400 error_code，details.unknown 列出它们。"""
    wanted = set(codes)
    found = (await session.scalars(select(model).where(model.code.in_(wanted)).order_by(model.code))).all()
    unknown = sorted(wanted - {item.code for item in found})
    if unknown:
        raise AppError(400, error_code, f"{what}不存在：{', '.join(unknown)}", {"unknown": unknown})
    return list(found)


async def _locked[M: (User, Role, Dept)](
    session: AsyncSession, model: type[M], key: int | str, what: str
) -> M:
    """按主键锁定一行（SELECT ... FOR UPDATE），不存在时 404。"""
    (pk,) = inspect(model).primary_key
    row = await session.scalar(select(model).where(pk == key).with_for_update())
    if row is None:
        raise not_found(what, key)
    return row


def _perm_codes(roles: list[Role]) -> set[str]:
    return {p.code for r in roles for p in r.perms}


def _ensure_within(actor: CurrentUser, perms: set[str]) -> None:
    """操作者经手的权限码必须都是自己拥有的。"""
    excess = sorted(perms - set(actor.perms))
    if excess:
        raise AppError(
            403, "PERMISSION_ESCALATION", f"不能经手自己没有的权限：{', '.join(excess)}", {"excess": excess}
        )


async def _check_dept(session: AsyncSession, dept_id: int | None) -> None:
    if dept_id is not None and await session.get(Dept, dept_id) is None:
        raise AppError(400, "DEPT_NOT_FOUND", f"院系 {dept_id} 不存在")


# ---------------- 用户 ----------------


def user_out(user: User) -> s.UserAdmin:
    return s.UserAdmin(
        id=user.id,
        username=user.username,
        name=user.name,
        dept_id=user.dept_id,
        email=user.email,
        active=user.active,
        roles=sorted(r.code for r in user.roles),
        created_at=user.created_at,
    )


def _user_snapshot(user: User) -> dict:
    return {
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "dept_id": user.dept_id,
        "active": user.active,
        "roles": sorted(r.code for r in user.roles),
    }


async def list_users(
    session: AsyncSession,
    params: PageParams,
    *,
    keyword: str | None = None,
    dept_id: int | None = None,
    role: str | None = None,
    active: bool | None = None,
) -> Page[s.UserAdmin]:
    stmt = select(User)
    if keyword:
        stmt = stmt.where(
            User.username.icontains(keyword, autoescape=True) | User.name.icontains(keyword, autoescape=True)
        )
    if dept_id is not None:
        stmt = stmt.where(User.dept_id == dept_id)
    if role is not None:
        stmt = stmt.where(User.roles.any(Role.code == role))
    if active is not None:
        stmt = stmt.where(User.active.is_(active))
    return await paginate(session, stmt.order_by(User.id), params, user_out)


async def create_user(session: AsyncSession, actor: CurrentUser, body: s.UserCreate) -> s.UserAdmin:
    password_hash = await hash_password_async(body.password)
    with constraint_errors(USER_ERRORS):
        async with session.begin():
            if await session.scalar(select(User.id).where(User.username == body.username)) is not None:
                raise AppError(409, "USERNAME_EXISTS", f"用户名 {body.username} 已存在")
            await _check_dept(session, body.dept_id)
            roles = await _by_codes(session, Role, body.role_codes, "UNKNOWN_ROLE", "角色")
            _ensure_within(actor, _perm_codes(roles))
            user = User(
                username=body.username,
                name=body.name,
                email=body.email,
                dept_id=body.dept_id,
                password_hash=password_hash,
                active=True,
                roles=roles,
            )
            session.add(user)
            await session.flush()
            audit.record(
                session, "user", actor.id, "user.create", "user", user.id, after=_user_snapshot(user)
            )
    return user_out(user)


async def update_user(
    session: AsyncSession, actor: CurrentUser, user_id: int, body: s.UserUpdate
) -> s.UserAdmin:
    fields = body.model_fields_set
    if user_id == actor.id and body.active is False:
        raise AppError(409, "SELF_LOCKOUT", "不能停用自己的账号")
    password_hash = await hash_password_async(body.password) if body.password else None
    with constraint_errors(USER_ERRORS):
        async with session.begin():
            user = await _locked(session, User, user_id, "用户")
            _ensure_within(actor, _perm_codes(user.roles))
            before = _user_snapshot(user)
            if "dept_id" in fields:
                await _check_dept(session, body.dept_id)
            for field in fields & {"email", "dept_id"}:
                setattr(user, field, getattr(body, field))
            if body.name is not None:
                user.name = body.name
            if body.active is not None:
                user.active = body.active
            if password_hash is not None:
                user.password_hash = password_hash
            after = _user_snapshot(user)
            if after != before or password_hash is not None:
                changed = {k for k in after if after[k] != before[k]}
                audit.record(
                    session,
                    "user",
                    actor.id,
                    "user.update",
                    "user",
                    user.id,
                    before={k: before[k] for k in changed},
                    after={k: after[k] for k in changed} | ({"password": "reset"} if password_hash else {}),
                )
    return user_out(user)


async def set_user_roles(
    session: AsyncSession, actor: CurrentUser, user_id: int, body: s.UserRolesUpdate
) -> s.UserAdmin:
    with constraint_errors(USER_ERRORS):
        async with session.begin():
            user = await _locked(session, User, user_id, "用户")
            roles = await _by_codes(session, Role, body.role_codes, "UNKNOWN_ROLE", "角色")
            _ensure_within(actor, _perm_codes([*user.roles, *roles]))
            if user_id == actor.id and not any(p.code == "admin:user" for r in roles for p in r.perms):
                raise AppError(409, "SELF_LOCKOUT", "不能移除自己的用户管理权限（admin:user）")
            before = sorted(r.code for r in user.roles)
            after = [r.code for r in roles]
            if after != before:
                user.roles = roles
                audit.record(
                    session,
                    "user",
                    actor.id,
                    "user.set_roles",
                    "user",
                    user.id,
                    before={"roles": before},
                    after={"roles": after},
                )
                session.add(
                    new_notification(
                        user.id,
                        "common.roles_changed",
                        {"roles": "、".join(r.name for r in roles)},
                        channels=["inapp"],
                        ref={"module": "common", "type": "user", "id": user.id},
                    )
                )
    return user_out(user)


# ---------------- 角色与权限 ----------------


def role_out(role: Role, user_count: int) -> s.RoleOut:
    return s.RoleOut(
        code=role.code,
        name=role.name,
        builtin=role.builtin,
        perms=sorted(p.code for p in role.perms),
        user_count=user_count,
    )


async def _user_count(session: AsyncSession, code: str) -> int:
    return await session.scalar(select(func.count()).where(user_roles.c.role_code == code)) or 0


async def list_roles(session: AsyncSession) -> list[s.RoleOut]:
    counts = dict(
        (
            await session.execute(
                select(user_roles.c.role_code, func.count()).group_by(user_roles.c.role_code)
            )
        ).all()
    )
    roles = (await session.scalars(select(Role).order_by(Role.builtin.desc(), Role.code))).all()
    return [role_out(r, counts.get(r.code, 0)) for r in roles]


async def list_permissions(session: AsyncSession) -> list[s.PermissionOut]:
    perms = await session.scalars(select(Permission).order_by(Permission.module, Permission.code))
    return [s.PermissionOut.model_validate(p, from_attributes=True) for p in perms]


async def create_role(session: AsyncSession, actor: CurrentUser, body: s.RoleCreate) -> s.RoleOut:
    with constraint_errors(ROLE_ERRORS):
        async with session.begin():
            if await session.get(Role, body.code) is not None:
                raise AppError(409, "ROLE_EXISTS", f"角色编码 {body.code} 已存在")
            perms = await _by_codes(session, Permission, body.perms, "UNKNOWN_PERMISSION", "权限码")
            _ensure_within(actor, {p.code for p in perms})
            role = Role(code=body.code, name=body.name, builtin=False, perms=perms)
            session.add(role)
            await session.flush()
            out = role_out(role, 0)
            audit.record(
                session,
                "user",
                actor.id,
                "role.create",
                "role",
                role.code,
                after=out.model_dump(include={"name", "perms"}),
            )
    return out


async def update_role(session: AsyncSession, actor: CurrentUser, code: str, body: s.RoleUpdate) -> s.RoleOut:
    with constraint_errors(ROLE_ERRORS):
        async with session.begin():
            role = await _locked(session, Role, code, "角色")
            before = role_out(role, 0).model_dump(include={"name", "perms"})
            if body.name is not None and body.name != role.name:
                if role.builtin:
                    raise AppError(409, "BUILTIN_ROLE_IMMUTABLE", "预置角色不能改名")
                role.name = body.name
            if body.perms is not None:
                perms = await _by_codes(session, Permission, body.perms, "UNKNOWN_PERMISSION", "权限码")
                _ensure_within(actor, {p.code for p in perms} ^ {p.code for p in role.perms})
                missing = ADMIN_PERMS - {p.code for p in perms}
                if role.code == SYS_ADMIN_ROLE and missing:
                    raise AppError(
                        409, "BUILTIN_ROLE_IMMUTABLE", f"系统管理员角色必须保留 {'、'.join(sorted(missing))}"
                    )
                role.perms = perms
            out = role_out(role, await _user_count(session, code))
            after = out.model_dump(include={"name", "perms"})
            if after != before:
                audit.record(
                    session, "user", actor.id, "role.update", "role", code, before=before, after=after
                )
    return out


async def delete_role(session: AsyncSession, actor: CurrentUser, code: str) -> None:
    async with session.begin():
        role = await _locked(session, Role, code, "角色")
        if role.builtin:
            raise AppError(409, "BUILTIN_ROLE_IMMUTABLE", "预置角色不能删除")
        _ensure_within(actor, {p.code for p in role.perms})
        users = await _user_count(session, code)
        if users:
            raise AppError(409, "ROLE_IN_USE", f"还有 {users} 个用户拥有该角色，先调整这些用户的角色")
        before = role_out(role, 0).model_dump(include={"name", "perms"})
        await session.delete(role)
        audit.record(session, "user", actor.id, "role.delete", "role", code, before=before)


# ---------------- 院系 ----------------


async def list_depts(session: AsyncSession) -> list[s.DeptOut]:
    depts = await session.scalars(select(Dept).order_by(Dept.id))
    return [s.DeptOut.model_validate(d, from_attributes=True) for d in depts]


async def create_dept(session: AsyncSession, actor: CurrentUser, body: s.DeptIn) -> s.DeptOut:
    with constraint_errors(DEPT_ERRORS):
        async with session.begin():
            if await session.scalar(select(Dept.id).where(Dept.name == body.name)) is not None:
                raise AppError(409, "DEPT_EXISTS", f"院系 {body.name} 已存在")
            dept = Dept(name=body.name)
            session.add(dept)
            await session.flush()
            audit.record(session, "user", actor.id, "dept.create", "dept", dept.id, after={"name": dept.name})
    return s.DeptOut.model_validate(dept, from_attributes=True)


async def rename_dept(session: AsyncSession, actor: CurrentUser, dept_id: int, body: s.DeptIn) -> s.DeptOut:
    with constraint_errors(DEPT_ERRORS):
        async with session.begin():
            dept = await _locked(session, Dept, dept_id, "院系")
            if dept.name != body.name:
                taken = await session.scalar(
                    select(Dept.id).where(Dept.name == body.name, Dept.id != dept_id)
                )
                if taken is not None:
                    raise AppError(409, "DEPT_EXISTS", f"院系 {body.name} 已存在")
                audit.record(
                    session,
                    "user",
                    actor.id,
                    "dept.update",
                    "dept",
                    dept_id,
                    before={"name": dept.name},
                    after={"name": body.name},
                )
                dept.name = body.name
    return s.DeptOut.model_validate(dept, from_attributes=True)
