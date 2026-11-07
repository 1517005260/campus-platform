"""申请人：资格检查、提交、查询、撤回。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends

from app import room_service
from app import schemas as s

router = APIRouter(prefix="/api/v1/room", tags=["申请"], responses=ERROR_RESPONSES)

Applicant = CurrentUser


@router.get("/eligibility", summary="检查我是否有资格申请整教室", response_model=s.Eligibility)
async def eligibility(session: SessionDep, user: Applicant = Depends(require_perm("room:apply"))):
    """门槛：拥有 room:apply 权限，且近 violation_window_days 天在 M1 的违约次数 < max_violations。"""
    return await room_service.eligibility(session, user)


@router.post("/applications", summary="提交整教室申请", response_model=s.Application, status_code=201)
async def submit(
    body: s.ApplicationCreate,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply")),
):
    """校验：资格、教室允许整室预约、提前天数、与其他 pending/approved 申请时段不冲突。
    匹配审批流并快照到申请上，进入第 1 级审批。"""
    return await room_service.submit(session, user, body)


@router.get("/applications/mine", summary="我的申请", response_model=Page[s.Application])
async def mine(
    session: SessionDep,
    status: s.ApplicationStatus | None = None,
    user: Applicant = Depends(require_perm("room:apply")),
    p: PageParams = Depends(page_params),
):
    return await room_service.list_mine(session, user, status, p)


@router.get("/applications/{application_id}", summary="申请详情（含审批记录）", response_model=s.Application)
async def detail(
    application_id: int,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply", "room:approve")),
):
    return await room_service.detail(session, user, application_id)


@router.post("/applications/{application_id}/withdraw", summary="撤回申请", response_model=s.Application)
async def withdraw(
    application_id: int,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply")),
):
    """pending → withdrawn；approved → cancelled 并调用 M1 释放占用。"""
    return await room_service.withdraw(session, user, application_id)
