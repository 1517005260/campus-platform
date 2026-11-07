"""审批人：待办、通过、驳回；管理员：审批流与参数配置。"""

from campus_common.auth import CurrentUser, require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends

from app import room_service
from app import schemas as s

router = APIRouter(prefix="/api/v1/room", tags=["审批与配置"], responses=ERROR_RESPONSES)

Approver = CurrentUser


@router.get("/approvals/todo", summary="我的待审批", response_model=Page[s.ApplicationForApprover])
async def todo(
    session: SessionDep,
    user: Approver = Depends(require_perm("room:approve")),
    p: PageParams = Depends(page_params),
):
    """当前级别 scope=dept 时只列出申请人与审批人同院系的申请。"""
    return await room_service.todo(session, user, p)


@router.post("/applications/{application_id}/approve", summary="审批通过", response_model=s.Application)
async def approve(
    application_id: int,
    body: s.ApprovalAction,
    session: SessionDep,
    user: Approver = Depends(require_perm("room:approve")),
):
    """非最后一级：进入下一级并刷新 deadline_at。
    最后一级：调用 M1 POST /internal/v1/blocks 占用教室，成功后才把状态改为 approved；
    M1 调用失败则本地不变，返回 502。"""
    return await room_service.approve(session, user, application_id, body)


@router.post("/applications/{application_id}/reject", summary="驳回", response_model=s.Application)
async def reject(
    application_id: int,
    body: s.ApprovalAction,
    session: SessionDep,
    user: Approver = Depends(require_perm("room:approve")),
):
    return await room_service.reject(session, user, application_id, body)


@router.get("/flows", summary="审批流配置", response_model=list[s.ApprovalFlow])
async def get_flows(session: SessionDep, user=Depends(require_perm("room:flow_manage"))):
    return await room_service.get_flows(session)


@router.put("/flows", summary="更新审批流配置", response_model=list[s.ApprovalFlow])
async def put_flows(
    body: list[s.ApprovalFlow],
    session: SessionDep,
    user=Depends(require_perm("room:flow_manage")),
):
    """只影响之后提交的申请，在途申请使用提交时的快照。"""
    return await room_service.put_flows(session, body)


@router.get("/settings", summary="申请参数", response_model=s.RoomSettings)
async def get_settings(
    session: SessionDep,
    user=Depends(require_perm("room:flow_manage", "room:apply")),
):
    return await room_service.get_settings(session)


@router.put("/settings", summary="更新申请参数", response_model=s.RoomSettings)
async def put_settings(
    body: s.RoomSettings,
    session: SessionDep,
    user=Depends(require_perm("room:flow_manage")),
):
    return await room_service.put_settings(session, body)
