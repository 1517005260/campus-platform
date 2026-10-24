"""M3 对其他模块的调用：只写业务语义，通信、桩数据与幂等键由 campus_common.clients 处理。"""

from datetime import datetime

from campus_common.clients import idempotency_key
from campus_common.clients.common import CommonClient, UserBrief
from campus_common.clients.m1 import M1BlockResult, M1Client, M1Room

from app.config import settings

m1 = M1Client(settings)
common = CommonClient(settings)


async def get_room(room_id: int) -> M1Room:
    return await m1.get_room(room_id)


async def block_room(order_id: int, room_id: int, start_at: datetime, reason: str) -> M1BlockResult:
    """开始维修且 blocks_room=true 时下架整间教室；维修结束时间未知（end_at 为空）。"""
    return await m1.create_block(
        source="M3_MAINTENANCE",
        ref_id=order_id,
        room_id=room_id,
        start_at=start_at,
        end_at=None,
        reason=reason,
        idempotency_key=idempotency_key(settings, "order", order_id, "block"),
    )


async def release_room(order_id: int) -> bool:
    """验收通过（含管理员代验收）时恢复教室。幂等。"""
    return await m1.release_block("M3_MAINTENANCE", order_id)


async def users_with_perm(perm: str) -> list[UserBrief]:
    """维修工（repair:work）或升级通知对象（repair:manage）。"""
    return await common.users_with_perm(perm)
