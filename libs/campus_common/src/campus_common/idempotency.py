"""服务间写接口的幂等处理（提供方使用）。

调用方在请求头带 Idempotency-Key（格式 <模块>-<实体>-<id>-<动作>，例如 m3-order-7-block）。
同一调用方的同一个 key，无论重试多少次、是否并发，业务只执行一次，后续请求返回首次的结果。
同一个 key 带着不同的请求内容到达时返回 409 IDEMPOTENCY_KEY_REUSED，避免把首次结果误当作这次的结果。

    return await run_idempotent(session, IdempotencyKey, caller, key, body, do_create, BlockResult)

约定：action 只修改会话中的数据、不自己提交；run_idempotent 在写入幂等记录后统一提交，
业务数据与幂等记录在同一事务中，咨询锁持有到提交为止。
"""

import hashlib
from collections.abc import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from campus_common.errors import AppError


def request_fingerprint(request: BaseModel) -> str:
    return hashlib.sha256(request.model_dump_json().encode()).hexdigest()


async def run_idempotent[T: BaseModel](
    session: AsyncSession,
    key_model,
    caller: str,
    key: str,
    request: BaseModel,
    action: Callable[[], Awaitable[T]],
    response_model: type[T],
) -> T:
    fingerprint = request_fingerprint(request)
    # 事务级咨询锁：同一 (caller, key) 的并发请求在这里排队
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"{caller}:{key}"}
    )
    existing = await session.get(key_model, (caller, key))
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键对应了不同的请求内容")
        return response_model.model_validate(existing.response)

    result = await action()
    session.add(
        key_model(
            caller=caller,
            key=key,
            request_hash=fingerprint,
            status_code=200,
            response=result.model_dump(mode="json"),
        )
    )
    await session.commit()
    return result
