"""M2 对 M1 的调用：只写业务语义，通信、桩数据与幂等键由 campus_common.clients 处理。

审批人和申请人的显示信息来自登录凭证，通知收件人由 common 按权限码与院系解析，因此 M2 不调用 common。
"""

from datetime import datetime

from campus_common.clients import idempotency_key
from campus_common.clients.m1 import M1BlockResult, M1Client, M1Room

from app.config import settings
from app.models import Application

m1 = M1Client(settings)

BLOCK_REASON_MAX = 200  # M1 占用原因的长度上限


async def get_room(room_id: int) -> M1Room:
    return await m1.get_room(room_id)


async def occupy_room(application: Application) -> M1BlockResult:
    """最终审批通过时占用教室，原因是申请用途（M1 通知被取消预约的学生"整教室借用：<用途>"）。

    幂等键 m2-app-{id}-occupy；请求内容只取申请上不可变的字段，重试发出的请求完全相同。"""
    return await m1.create_block(
        source="M2_OCCUPY",
        ref_id=application.id,
        room_id=application.room_id,
        start_at=application.start_at,
        end_at=application.end_at,
        reason=application.purpose[:BLOCK_REASON_MAX],
        idempotency_key=idempotency_key(settings, "app", application.id, "occupy"),
    )


async def release_room(application_id: int) -> bool:
    """释放占用。幂等：没有占用或已释放时返回 False。"""
    return await m1.release_block("M2_OCCUPY", application_id)


async def count_affected_reservations(room_id: int, start_at: datetime, end_at: datetime) -> int:
    return len(await m1.room_reservations(room_id, start_at, end_at))


async def violation_count(user_id: int, since: datetime) -> int:
    return await m1.violation_count(user_id, since)
