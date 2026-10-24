"""消费结果判定：不依赖 RabbitMQ，处理函数用假实现。"""

from campus_common.consuming import TopologyCheck, decide_outcome
from campus_common.events import Envelope, NotificationSend
from campus_common.retry import Action, ErrorKind, PermanentError, RetryPolicy
from campus_common.topology import RETRY_HEADER
from sqlalchemy import exc as sa_exc

POLICY = RetryPolicy(inline_delays=(0, 0))
BODY = (
    Envelope(
        type="notification.send",
        producer="m1-seat",
        payload=NotificationSend(user_ids=[1], template="t").model_dump(mode="json"),
    )
    .model_dump_json()
    .encode()
)


async def no_sleep(_):
    return None


def failing(*errors):
    calls = []

    async def handler(envelope):
        calls.append(envelope)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]

    handler.calls = calls
    return handler


def db_down():
    return sa_exc.OperationalError("select", {}, ConnectionRefusedError())


async def run(handler, headers=None, body=BODY):
    return await decide_outcome(body, headers, handler, POLICY, sleep=no_sleep)


async def test_success_acks():
    h = failing()
    assert (await run(h)).action is Action.ACK
    assert len(h.calls) == 1


async def test_malformed_envelope_dead_letters_without_calling_handler():
    h = failing()
    out = await run(h, body=b'{"hello": "world"}')
    assert (out.action, out.kind) == (Action.DEAD_LETTER, ErrorKind.PERMANENT)
    assert h.calls == []


async def test_permanent_error_dead_letters_immediately():
    h = failing(PermanentError("bad"))
    out = await run(h)
    assert (out.action, out.kind) == (Action.DEAD_LETTER, ErrorKind.PERMANENT)
    assert len(h.calls) == 1  # 不做进程内重试


async def test_transient_blip_recovered_inline():
    h = failing(db_down(), db_down())  # 两次进程内重试内恢复
    assert (await run(h)).action is Action.ACK
    assert len(h.calls) == 3


async def test_transient_outage_goes_to_delayed_retry_with_counter():
    h = failing(*[db_down()] * 3)
    out = await run(h, headers={RETRY_HEADER: 2})
    assert (out.action, out.kind, out.retries, out.delay) == (Action.RETRY, ErrorKind.TRANSIENT, 3, 120)
    assert "OperationalError" in out.error


async def test_unknown_error_retried_without_inline_attempts_then_dead_lettered():
    h = failing(RuntimeError("unexpected state"))
    out = await run(h)
    assert (out.action, out.retries, out.delay) == (Action.RETRY, 1, 5)
    assert len(h.calls) == 1
    out = await run(failing(RuntimeError("unexpected state")), headers={RETRY_HEADER: 3})
    assert (out.action, out.kind) == (Action.DEAD_LETTER, ErrorKind.UNKNOWN)


async def test_bad_retry_header_treated_as_zero():
    out = await run(failing(RuntimeError()), headers={RETRY_HEADER: "x"})
    assert out.retries == 1


def test_missing_retry_queue_does_not_require_restart():
    check = TopologyCheck(missing=("common.notification.send.retry.5s",), idle=())
    assert not check.subscriptions_lost({"common.notification.send"})


def test_missing_or_idle_own_queue_requires_restart():
    own = {"common.notification.send"}
    assert TopologyCheck(missing=("common.notification.send",), idle=()).subscriptions_lost(own)
    assert TopologyCheck(missing=(), idle=("common.notification.send",)).subscriptions_lost(own)
