"""服务间写接口的幂等：同一调用方同一个 key 只执行一次，并发也一样；同键不同请求被拒绝。"""

import asyncio

import pytest
from app.config import settings
from app.models import IdempotencyKey
from campus_common.db import make_async_sessionmaker
from campus_common.errors import AppError
from campus_common.idempotency import run_idempotent
from pydantic import BaseModel

pytestmark = pytest.mark.db


class Request(BaseModel):
    room_id: int


class Result(BaseModel):
    block_id: int


@pytest.fixture
async def sessions(db):
    maker = make_async_sessionmaker(settings.database_url)
    yield maker
    await maker.kw["bind"].dispose()


def counting_action(calls: list[int], block_id: int = 7):
    async def action() -> Result:
        calls.append(1)
        await asyncio.sleep(0.05)  # 让并发请求在锁上真正重叠
        return Result(block_id=block_id)

    return action


async def run(sessions, key: str, request: Request, action) -> Result:
    async with sessions() as session:
        return await run_idempotent(session, IdempotencyKey, "m3-repair", key, request, action, Result)


async def test_repeated_request_returns_first_result_without_reexecuting(sessions):
    calls: list[int] = []
    first = await run(sessions, "m3-order-7-block", Request(room_id=3), counting_action(calls, 7))
    second = await run(sessions, "m3-order-7-block", Request(room_id=3), counting_action(calls, 99))
    assert first == second == Result(block_id=7)
    assert len(calls) == 1


async def test_concurrent_requests_with_same_key_execute_once(sessions):
    calls: list[int] = []
    results = await asyncio.gather(
        *(run(sessions, "m3-order-8-block", Request(room_id=3), counting_action(calls)) for _ in range(5))
    )
    assert len(calls) == 1
    assert {r.block_id for r in results} == {7}


async def test_same_key_with_different_request_is_rejected(sessions):
    await run(sessions, "m3-order-9-block", Request(room_id=3), counting_action([]))
    with pytest.raises(AppError) as exc:
        await run(sessions, "m3-order-9-block", Request(room_id=4), counting_action([]))
    assert (exc.value.status, exc.value.code) == (409, "IDEMPOTENCY_KEY_REUSED")


async def test_failed_action_leaves_no_record_and_can_be_retried(sessions):
    async def failing() -> Result:
        raise RuntimeError("M1 内部错误")

    with pytest.raises(RuntimeError):
        await run(sessions, "m3-order-10-block", Request(room_id=3), failing)
    calls: list[int] = []
    assert await run(sessions, "m3-order-10-block", Request(room_id=3), counting_action(calls)) == Result(
        block_id=7
    )
    assert len(calls) == 1


async def test_keys_are_scoped_per_caller(sessions):
    calls: list[int] = []
    async with sessions() as session:
        await run_idempotent(
            session, IdempotencyKey, "m2-room", "k-1", Request(room_id=3), counting_action(calls), Result
        )
    async with sessions() as session:
        await run_idempotent(
            session, IdempotencyKey, "m3-repair", "k-1", Request(room_id=3), counting_action(calls), Result
        )
    assert len(calls) == 2
