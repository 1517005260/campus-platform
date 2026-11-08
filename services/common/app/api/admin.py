"""用户、角色、权限、院系管理（规则见 app/rbac.py）。

角色、权限与院系的变化写进 token，在用户下次登录后生效（token 有效期内旧权限仍然有效，ADR-002）。
"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends, Query

from app import rbac
from app import schemas as s

router = APIRouter(prefix="/api/v1/admin", tags=["系统管理"], responses=ERROR_RESPONSES)

ADMIN_USER = Depends(require_perm("admin:user"))
ADMIN_ROLE = Depends(require_perm("admin:role"))


# ---------------- 用户 ----------------


@router.get("/users", summary="用户列表", response_model=Page[s.UserAdmin])
async def list_users(
    session: SessionDep,
    keyword: str | None = Query(None, description="用户名或姓名包含该文本（不区分大小写）"),
    dept_id: int | None = None,
    role: str | None = Query(None, description="角色编码"),
    active: bool | None = Query(None, description="true 只看启用的，false 只看停用的"),
    p: PageParams = Depends(page_params),
    user: CurrentUser = ADMIN_USER,
):
    """按 ID 升序。"""
    return await rbac.list_users(session, p, keyword=keyword, dept_id=dept_id, role=role, active=active)


@router.post("/users", summary="新建用户", response_model=s.UserAdmin, status_code=201)
async def create_user(body: s.UserCreate, session: SessionDep, user: CurrentUser = ADMIN_USER):
    """错误：409 `USERNAME_EXISTS`；400 `DEPT_NOT_FOUND`、`UNKNOWN_ROLE`；
    403 `PERMISSION_ESCALATION`（分配的角色含自己没有的权限码）。"""
    return await rbac.create_user(session, user, body)


@router.patch(
    "/users/{user_id}", summary="修改用户（资料、院系、停用/启用、重置密码）", response_model=s.UserAdmin
)
async def update_user(user_id: int, body: s.UserUpdate, session: SessionDep, user: CurrentUser = ADMIN_USER):
    """停用的用户不能登录，也不再出现在按权限查用户的结果中；已签发的 token 到期前仍然有效。

    错误：404 `NOT_FOUND`；400 `DEPT_NOT_FOUND`；409 `SELF_LOCKOUT`（停用自己）；
    403 `PERMISSION_ESCALATION`（该用户的角色含自己没有的权限码）。"""
    return await rbac.update_user(session, user, user_id, body)


@router.put("/users/{user_id}/roles", summary="设置用户角色", response_model=s.UserAdmin)
async def set_user_roles(
    user_id: int, body: s.UserRolesUpdate, session: SessionDep, user: CurrentUser = ADMIN_USER
):
    """整体替换用户的角色，并给该用户发一条站内通知。角色变化在用户下次登录后生效。

    错误：404 `NOT_FOUND`；400 `UNKNOWN_ROLE`；409 `SELF_LOCKOUT`（移除自己的 admin:user）；
    403 `PERMISSION_ESCALATION`（原有或新分配的角色含自己没有的权限码）。"""
    return await rbac.set_user_roles(session, user, user_id, body)


# ---------------- 角色与权限 ----------------


@router.get("/roles", summary="角色列表", response_model=list[s.RoleOut])
async def list_roles(
    session: SessionDep, user: CurrentUser = Depends(require_perm("admin:role", "admin:user"))
):
    """预置角色在前。`admin:user` 也可查看，用于给用户分配角色。"""
    return await rbac.list_roles(session)


@router.post("/roles", summary="新建角色", response_model=s.RoleOut, status_code=201)
async def create_role(body: s.RoleCreate, session: SessionDep, user: CurrentUser = ADMIN_ROLE):
    """新建的角色为自定义角色（builtin=false）。

    错误：400 `UNKNOWN_PERMISSION`（details.unknown 列出不存在的权限码）；409 `ROLE_EXISTS`。"""
    return await rbac.create_role(session, user, body)


@router.patch("/roles/{code}", summary="修改角色", response_model=s.RoleOut)
async def update_role(code: str, body: s.RoleUpdate, session: SessionDep, user: CurrentUser = ADMIN_ROLE):
    """perms 为整体替换。预置角色可以调整权限，不能改名；系统管理员角色必须保留 admin:user 与 admin:role。

    错误：404 `NOT_FOUND`；400 `UNKNOWN_PERMISSION`；409 `BUILTIN_ROLE_IMMUTABLE`。"""
    return await rbac.update_role(session, user, code, body)


@router.delete("/roles/{code}", summary="删除自定义角色", status_code=204)
async def delete_role(code: str, session: SessionDep, user: CurrentUser = ADMIN_ROLE) -> None:
    """错误：404 `NOT_FOUND`；409 `BUILTIN_ROLE_IMMUTABLE`（预置角色）、
    `ROLE_IN_USE`（仍有用户拥有该角色）。"""
    await rbac.delete_role(session, user, code)


@router.get("/permissions", summary="权限码目录", response_model=list[s.PermissionOut])
async def list_permissions(session: SessionDep, user: CurrentUser = ADMIN_ROLE):
    """按模块、权限码排序。权限码由各模块在 common 的 app/permissions.py 登记，部署时由种子写入。"""
    return await rbac.list_permissions(session)


# ---------------- 院系 ----------------


@router.get("/depts", summary="院系列表", response_model=list[s.DeptOut])
async def list_depts(
    session: SessionDep,
    user: CurrentUser = Depends(
        require_perm("admin:user", "room:approve", "room:approve_school", "seat:room_manage")
    ),
):
    """按 ID 升序。"""
    return await rbac.list_depts(session)


@router.post("/depts", summary="新建院系", response_model=s.DeptOut, status_code=201)
async def create_dept(body: s.DeptIn, session: SessionDep, user: CurrentUser = ADMIN_USER):
    """错误：409 `DEPT_EXISTS`。"""
    return await rbac.create_dept(session, user, body)


@router.patch("/depts/{dept_id}", summary="院系改名", response_model=s.DeptOut)
async def rename_dept(dept_id: int, body: s.DeptIn, session: SessionDep, user: CurrentUser = ADMIN_USER):
    """院系不能删除（其他模块按院系 ID 引用院系），撤销的院系改名标注即可。

    错误：404 `NOT_FOUND`；409 `DEPT_EXISTS`。"""
    return await rbac.rename_dept(session, user, dept_id, body)
