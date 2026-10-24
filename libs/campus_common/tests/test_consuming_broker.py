"""subscribe() 接入 FastStream 后的端到端行为（内存中的 TestRabbitBroker，不需要 RabbitMQ）。"""

import pytest
from campus_common.consuming import create_broker, subscribe
from campus_common.events import DEAD_LETTER_EXCHANGE, Envelope, NotificationSend
from campus_common.retry import PermanentError, RetryPolicy
from campus_common.topology import (
    ERROR_HEADER,
    ERROR_KIND_HEADER,
    FAILED_AT_HEADER,
    NOTIFICATION_QUEUE,
    RETRY_HEADER,
    ROUTING_KEY_HEADER,
)

faststream = pytest.importorskip("faststream")
from faststream.rabbit import RabbitQueue, TestRabbitBroker  # noqa: E402

ENVELOPE = Envelope(
    type="notification.send",
    producer="m1-seat",
    payload=NotificationSend(user_ids=[1], template="t").model_dump(mode="json"),
)


def make(handler):
    broker = create_broker("amqp://guest:guest@localhost:5672//")
    subscribe(broker, NOTIFICATION_QUEUE, handler, RetryPolicy(inline_delays=()))
    retry = broker.subscriber(RabbitQueue(NOTIFICATION_QUEUE.retry_queue(5)))(lambda m: None)
    dead = broker.subscriber(
        RabbitQueue(NOTIFICATION_QUEUE.dead_letter_queue, routing_key=NOTIFICATION_QUEUE.name),
        DEAD_LETTER_EXCHANGE,
    )(lambda m: None)
    return broker, retry, dead


async def publish(broker, body):
    await broker.publish(body, queue=NOTIFICATION_QUEUE.name, content_type="application/json")


async def test_handler_receives_envelope():
    received = []

    async def handler(envelope):
        received.append(envelope)

    broker, retry, dead = make(handler)
    async with TestRabbitBroker(broker) as br:
        await publish(br, ENVELOPE.model_dump_json().encode())
        retry.mock.assert_not_called()
        dead.mock.assert_not_called()
    assert [e.message_id for e in received] == [ENVELOPE.message_id]


async def test_unknown_error_goes_to_retry_queue_with_counter():
    async def handler(envelope):
        raise RuntimeError("unexpected state")

    broker, retry, dead = make(handler)
    async with TestRabbitBroker(broker) as br:
        await publish(br, ENVELOPE.model_dump_json().encode())
        assert retry.mock.call_count == 1
        dead.mock.assert_not_called()


async def test_malformed_message_goes_to_dead_letter_queue_without_calling_handler():
    received = []

    async def handler(envelope):
        received.append(envelope)

    broker, retry, dead = make(handler)
    async with TestRabbitBroker(broker) as br:
        await publish(br, b'{"hello": "world"}')  # 合法 JSON，但不是 Envelope
        assert dead.mock.call_count == 1
        retry.mock.assert_not_called()
    assert received == []


async def test_permanent_error_from_handler_goes_to_dead_letter_queue():
    async def handler(envelope):
        raise PermanentError("用户不存在")

    broker, retry, dead = make(handler)
    async with TestRabbitBroker(broker) as br:
        await publish(br, ENVELOPE.model_dump_json().encode())
        assert dead.mock.call_count == 1
        retry.mock.assert_not_called()


def test_header_names_are_stable():
    # mqctl 与死信队列中的消息依赖这些消息头，改名属于破坏性变更
    assert (RETRY_HEADER, ERROR_KIND_HEADER, ERROR_HEADER, ROUTING_KEY_HEADER, FAILED_AT_HEADER) == (
        "x-campus-retry",
        "x-campus-error-kind",
        "x-campus-error",
        "x-campus-routing-key",
        "x-campus-failed-at",
    )
