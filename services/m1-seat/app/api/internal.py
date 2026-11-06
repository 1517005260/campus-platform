"""跨模块接口，只在 Docker 内网中可达，网关不转发 /internal。

M1 是座位状态的唯一写入方：M2、M3 通过这里占用和释放教室，不直接写 M1 的表。
改动本文件的接口签名需要 M2、M3 负责人评审。
"""

from typing import Annotated

from campus_common.auth import require_service
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.idempotency import run_idempotent
from campus_common.query import query_model
from fastapi import APIRouter, Depends, Header
from pydantic import AwareDatetime

from app import block_service
from app import schemas as s
from app.models import IdempotencyKey

router = APIRouter(prefix="/internal/v1", tags=["internal"], responses=ERROR_RESPONSES)

Caller = Annotated[str, Depends(require_service("m2-room", "m3-repair"))]


@router.get("/rooms/{room_id}", summary="查询教室（含座位）", response_model=s.RoomDetail)
async def internal_get_room(room_id: int, caller: Caller, session: SessionDep):
    """不论启用状态与院系，返回教室及其全部座位（含停用的座位，M3 上报故障时用来校验座位归属）。

    教室不存在：404 `NOT_FOUND`。"""
    return await block_service.get_room(session, room_id)


@router.post("/blocks", summary="占用或下架整间教室", response_model=s.InternalBlockResult)
async def create_block(
    body: s.InternalBlockCreate,
    caller: Caller,
    idempotency_key: Annotated[str, Header(description="例如 m3-order-7-block")],
    session: SessionDep,
):
    """在 [start_at, end_at) 内下架该教室全部座位，并记录写入来源 (source, ref_id)。

    时段内已有的个人预约自动取消（cancel_reason=BLOCKED_BY_M2/M3）、通知学生、不记违约，
    在返回值中列出。

    先按幂等键处理：同一幂等键 + 同样的请求，无论占用后来是否已释放，都原样重放首次结果（200）；
    同一幂等键 + 不同的请求返回 409 `IDEMPOTENCY_KEY_REUSED`。M2、M3 的键按单号固定
    （`m2-app-{id}-occupy`、`m3-order-{id}-block`），因此它们重发同一单号只会走到这一步。
    换了幂等键时再按 (source, ref_id) 处理：一个单号只对应一次占用，已释放返回 409 `BLOCK_ALREADY_RELEASED`，
    请求不同返回 409 `BLOCK_REFERENCE_CONFLICT`，相同则返回已有的 block_id 且不再取消预约。

    其他错误：403 `BLOCK_SOURCE_FORBIDDEN`（source 与调用方不符）；404 `NOT_FOUND`（教室不存在）；
    422 `VALIDATION_ERROR`（end_at 不晚于 start_at）。
    """
    return await run_idempotent(
        session,
        IdempotencyKey,
        caller,
        idempotency_key,
        body,
        lambda: block_service.create_block(session, caller, body),
        s.InternalBlockResult,
    )


@router.delete("/blocks/{source}/{ref_id}", summary="释放占用", response_model=s.InternalReleaseResult)
async def release_block(source: s.BlockSource, ref_id: int, caller: Caller, session: SessionDep):
    """M2 撤销/超时、M3 验收通过时调用。幂等：不存在或已释放时返回 released=false。

    source 与调用方不符：403 `BLOCK_SOURCE_FORBIDDEN`。"""
    async with session.begin():
        released = await block_service.release_block(session, caller, source, ref_id)
    return s.InternalReleaseResult(released=released)


@router.get(
    "/rooms/{room_id}/reservations",
    summary="查询时段内的有效个人预约",
    response_model=list[s.Reservation],
)
async def room_reservations(
    room_id: int,
    span: Annotated[s.InternalTimeRange, Depends(query_model(s.InternalTimeRange))],
    caller: Caller,
    session: SessionDep,
):
    """M2 审批人审批前查看"批准后会影响多少人"。

    教室不存在：404 `NOT_FOUND`；end_at 不晚于 start_at：422 `VALIDATION_ERROR`。"""
    return await block_service.room_reservations(session, room_id, span)


@router.get(
    "/users/{user_id}/violations",
    summary="用户违约次数",
    response_model=s.InternalViolationCount,
)
async def violation_count(
    user_id: int,
    since: AwareDatetime,
    caller: Annotated[str, Depends(require_service("m2-room"))],
    session: SessionDep,
):
    """统计 created_at >= since 的违约次数（含 since 时刻）。

    只允许 M2 调用，其他服务：403 `SERVICE_FORBIDDEN`。"""
    return await block_service.violation_count(session, user_id, since)
