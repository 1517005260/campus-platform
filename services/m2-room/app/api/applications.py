"""申请人：资格检查、提交、查询、撤回与取消。"""

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
    """门槛：拥有 room:apply 权限，且近 violation_window_days 天在 M1 的违约次数 < max_violations。

    M1 不可用时 502 UPSTREAM_UNAVAILABLE。"""
    return await room_service.eligibility(session, user)


@router.post("/applications", summary="提交整教室申请", response_model=s.Application, status_code=201)
async def submit(
    body: s.ApplicationCreate,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply")),
):
    """校验通过后匹配审批流并快照到申请上，进入第 1 级审批，通知第 1 级审批人。错误码：

    - 400 ADVANCE_DAYS_OUT_OF_RANGE：开始时间不晚于现在，或开始日期（业务时区）不在今天之后
      advance_days_min–advance_days_max 天内
    - 403 NOT_ELIGIBLE：违约次数达到上限，details 为原因列表
    - 400 ROOM_NOT_BOOKABLE：教室停用或不允许整教室预约
    - 403 DEPT_RESTRICTED：院系教室只接受本院系申请人
    - 400 ATTENDEES_EXCEED_CAPACITY：参加人数超过教室容量
    - 400 OUTSIDE_OPEN_HOURS：时段不在教室当天的开放时间内（也因此不能跨天）
    - 409 APPROVAL_FLOW_NOT_FOUND：没有适用于该教室的审批流
    - 400 APPLICANT_DEPT_REQUIRED：审批流含院系级审批而申请人不属于任何院系
    - 409 APPLICATION_TIME_CONFLICT：与该教室其他 pending/approved 申请时段重叠
    - 404 NOT_FOUND（教室不存在）、502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR：来自 M1
    """
    return await room_service.submit(session, user, body)


@router.get("/applications/mine", summary="我的申请", response_model=Page[s.Application])
async def mine(
    session: SessionDep,
    status: s.ApplicationStatus | None = None,
    user: Applicant = Depends(require_perm("room:apply")),
    p: PageParams = Depends(page_params),
):
    """按提交时间倒序。"""
    return await room_service.list_mine(session, user, status, p)


@router.get("/applications/{application_id}", summary="申请详情（含审批记录）", response_model=s.Application)
async def detail(
    application_id: int,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply", "room:approve", "room:approve_school")),
):
    """申请人本人、审批过该申请的人、能审批其中任一级的人（权限码与院系范围）可以查看，
    其他人 404 NOT_FOUND。"""
    return await room_service.detail(session, user, application_id)


@router.post(
    "/applications/{application_id}/withdraw", summary="撤回或取消申请", response_model=s.Application
)
async def withdraw(
    application_id: int,
    session: SessionDep,
    user: Applicant = Depends(require_perm("room:apply")),
):
    """pending → withdrawn，通知当前级别审批人；approved 且未开始 → 先经 M1 释放教室，成功后 cancelled，
    通知审批通过过该申请的人。错误码：

    - 404 NOT_FOUND：看不到该申请；403 FORBIDDEN：不是申请人
    - 409 APPLICATION_STATE_CONFLICT：已结束、已开始的已通过申请，或并发修改
    - 409 OCCUPY_IN_PROGRESS：撤回 pending 申请时，最终审批正在向 M1 申请占用教室（请求后 1 分钟内），稍后再试
    - 502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR：取消时 M1 释放失败，申请保持 approved，可重试
    """
    return await room_service.withdraw(session, user, application_id)
