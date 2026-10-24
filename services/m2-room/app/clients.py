"""M2 对其他模块的调用：只写业务语义，通信、桩数据与幂等键由 campus_common.clients 处理。"""

from datetime import datetime

from campus_common.clients import idempotency_key
from campus_common.clients.common import CommonClient, UserBrief
from campus_common.clients.m1 import M1BlockResult, M1Client, M1Room

from app.config import settings

m1 = M1Client(settings)
common = CommonClient(settings)


async def get_room(room_id: int) -> M1Room:
    return await m1.get_room(room_id)


async def occupy_room(
    application_id: int, room_id: int, start_at: datetime, end_at: datetime, reason: str
) -> M1BlockResult:
    """最终审批通过时占用教室。幂等键 m2-app-{id}-occupy，重试安全。"""
    return await m1.create_block(
        source="M2_OCCUPY",
        ref_id=application_id,
        room_id=room_id,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
        idempotency_key=idempotency_key(settings, "app", application_id, "occupy"),
    )


async def release_room(application_id: int) -> bool:
    """已通过的申请被撤销或取消时释放占用。幂等。"""
    return await m1.release_block("M2_OCCUPY", application_id)


async def count_affected_reservations(room_id: int, start_at: datetime, end_at: datetime) -> int:
    return len(await m1.room_reservations(room_id, start_at, end_at))


async def violation_count(user_id: int, since: datetime) -> int:
    return await m1.violation_count(user_id, since)


async def users_with_perm(perm: str, dept_id: int | None = None) -> list[UserBrief]:
    """查找审批人，例如本院系拥有 room:approve 的用户（scope=dept 时传申请人院系）。"""
    return await common.users_with_perm(perm, dept_id)
