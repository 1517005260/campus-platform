"""用户、角色、权限、院系管理。"""

from campus_common.auth import require_perm
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_of, page_params
from fastapi import APIRouter, Depends

from app import schemas as s
from app import stubs

router = APIRouter(prefix="/api/v1/admin", tags=["系统管理"], responses=ERROR_RESPONSES)

ADMIN_USER = Depends(require_perm("admin:user"))
ADMIN_ROLE = Depends(require_perm("admin:role"))


@router.get("/users", summary="用户列表", response_model=Page[s.UserAdmin])
async def list_users(
    keyword: str | None = None,
    dept_id: int | None = None,
    role: str | None = None,
    p: PageParams = Depends(page_params),
    user=ADMIN_USER,
):
    return page_of([stubs.user()], 1, p)


@router.post("/users", summary="新建用户", response_model=s.UserAdmin, status_code=201)
async def create_user(body: s.UserCreate, user=ADMIN_USER):
    return stubs.user()


@router.put("/users/{user_id}/roles", summary="设置用户角色", response_model=s.UserAdmin)
async def set_user_roles(user_id: int, body: s.UserRolesUpdate, user=ADMIN_USER):
    """角色变化在用户下次登录（或 token 过期）后生效。"""
    return stubs.user()


@router.get("/roles", summary="角色列表", response_model=list[s.RoleOut])
async def list_roles(user=ADMIN_ROLE):
    return stubs.roles()


@router.post("/roles", summary="新建角色", response_model=s.RoleOut, status_code=201)
async def create_role(body: s.RoleCreate, user=ADMIN_ROLE):
    """perms 中的每个权限码必须存在于权限目录，否则 400 UNKNOWN_PERMISSION。"""
    return stubs.role(body.code, body.name, body.perms)


@router.patch("/roles/{code}", summary="修改角色", response_model=s.RoleOut)
async def update_role(code: str, body: s.RoleUpdate, user=ADMIN_ROLE):
    return stubs.role(code, body.name, body.perms)


@router.get("/permissions", summary="权限码目录", response_model=list[s.PermissionOut])
async def list_permissions(user=ADMIN_ROLE):
    return stubs.permissions()


@router.get("/depts", summary="院系列表", response_model=list[s.DeptOut])
async def list_depts(user=Depends(require_perm("admin:user", "room:approve", "seat:room_manage"))):
    return stubs.depts()
