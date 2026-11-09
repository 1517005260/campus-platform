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
APPROVER_PERMS = ("room:approve", "room:approve_school")


@router.get("/approvals/todo", summary="我的待审批", response_model=Page[s.ApplicationForApprover])
async def todo(
    session: SessionDep,
    user: Approver = Depends(require_perm(*APPROVER_PERMS)),
    p: PageParams = Depends(page_params),
):
    """当前用户此刻能通过或驳回的申请（与审批时的检查是同一组条件），按截止时间排序。
    affected_reservations 逐条向 M1 查询，失败时为空。"""
    return await room_service.todo(session, user, p)


@router.post("/applications/{application_id}/approve", summary="审批通过", response_model=s.Application)
async def approve(
    application_id: int,
    body: s.ApprovalAction,
    session: SessionDep,
    user: Approver = Depends(require_perm(*APPROVER_PERMS)),
):
    """非最后一级：进入下一级并刷新 deadline_at，通知申请人与下一级审批人。
    最后一级：调用 M1 POST /internal/v1/blocks 占用教室（原因为申请用途），成功后才改为 approved。错误码：

    - 404 NOT_FOUND：看不到该申请
    - 409 APPLICATION_STATE_CONFLICT：申请已不在审批中，或被并发修改
    - 409 APPLICATION_EXPIRED：已到当前级别截止时间或申请时段已开始（等待自动撤销）
    - 403 NOT_YOUR_TURN：审批自己的申请、没有当前级别的权限码、院系级而不同院系、已审批过该申请的其他级别
    - 502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR 或 M1 的业务错误（原样返回，如 409 ROOM_UNDER_MAINTENANCE
      教室正在维修）：占用失败，申请保持 pending，可重试
    """
    return await room_service.approve(session, user, application_id, body)


@router.post("/applications/{application_id}/reject", summary="驳回", response_model=s.Application)
async def reject(
    application_id: int,
    body: s.ApprovalAction,
    session: SessionDep,
    user: Approver = Depends(require_perm(*APPROVER_PERMS)),
):
    """任一级驳回 → rejected，通知申请人（含级别与意见）。错误码：

    - 404 NOT_FOUND：看不到该申请
    - 409 APPLICATION_STATE_CONFLICT：申请已不在审批中，或被并发修改
    - 409 APPLICATION_EXPIRED：已到当前级别截止时间或申请时段已开始（等待自动撤销）
    - 403 NOT_YOUR_TURN：审批自己的申请、没有当前级别的权限码、院系级而不同院系、已审批过该申请的其他级别
    - 409 OCCUPY_IN_PROGRESS：最终审批正在向 M1 申请占用教室（请求后 1 分钟内），稍后再试
    """
    return await room_service.reject(session, user, application_id, body)


@router.get("/flows", summary="审批流配置", response_model=list[s.ApprovalFlow])
async def get_flows(session: SessionDep, user=Depends(require_perm("room:flow_manage"))):
    return await room_service.get_flows(session)


@router.put("/flows", summary="更新审批流配置", response_model=list[s.ApprovalFlow])
async def put_flows(
    body: s.FlowList,
    session: SessionDep,
    user=Depends(require_perm("room:flow_manage")),
):
    """整体替换，只影响之后提交的申请（在途申请使用提交时的快照）。
    至少一条；每级 approver_perm 须与 scope 对应（dept → room:approve，school → room:approve_school），
    否则 422 VALIDATION_ERROR；名称重复 409 DUPLICATE_FLOW_NAME。"""
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
    """advance_days_max 小于 advance_days_min 等校验失败时 422 VALIDATION_ERROR。"""
    return await room_service.put_settings(session, body)
