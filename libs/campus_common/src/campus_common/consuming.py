"""消费端运行时：解析消息 → 调用处理函数 → 按错误分类 ack / 延迟重试 / 进死信队列。

    from campus_common.consuming import subscribe
    from campus_common.topology import NOTIFICATION_QUEUE

    broker = create_broker(settings.rabbitmq_url)
    subscribe(broker, NOTIFICATION_QUEUE, handle_notification)   # handle_notification(envelope)

处理函数只负责业务：在 inbox 去重的事务里写库，出错直接抛异常。可靠性由这里统一处理：
- 永久错误（结构不合法等）直接进死信队列，不浪费重试；
- 临时错误先在进程内快速重试，仍失败则发到 <队列>.retry.<N>s，等待后自动回到原队列，
  依赖恢复后继续处理（比如数据库重启几分钟），不会因为短暂故障进死信队列；
- 重试与死信消息都带 x-campus-retry / x-campus-error-kind / x-campus-error 头，便于排查和重放；
- 先发布重试/死信副本（publisher confirm；目标队列不存在时 broker 退回，发布抛错），成功后才 ack
  原消息；中途崩溃最多导致重复，由 inbox 去重。

decide_outcome() 不依赖 RabbitMQ，测试直接调用；subscribe() 把它接到 FastStream 上（需要 campus-common[mq]）。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from campus_common.events import DEAD_LETTER_EXCHANGE, Envelope
from campus_common.retry import DEFAULT_POLICY, Action, ErrorKind, RetryPolicy, classify
from campus_common.timeutil import now
from campus_common.topology import (
    ERROR_HEADER,
    ERROR_KIND_HEADER,
    FAILED_AT_HEADER,
    RETRY_HEADER,
    ROUTING_KEY_HEADER,
    ConsumerQueue,
)

log = logging.getLogger(__name__)

Handler = Callable[[Envelope], Awaitable[None]]


@dataclass(frozen=True)
class Outcome:
    action: Action
    retries: int  # 发布副本时写入 x-campus-retry 的值
    delay: int | None = None
    kind: ErrorKind | None = None
    error: str | None = None


def retries_of(headers: Mapping[str, Any] | None) -> int:
    try:
        return max(int((headers or {}).get(RETRY_HEADER, 0)), 0)
    except (TypeError, ValueError):
        return 0


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


async def decide_outcome(
    body: bytes,
    headers: Mapping[str, Any] | None,
    handler: Handler,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> Outcome:
    retries = retries_of(headers)
    try:
        envelope = Envelope.model_validate_json(body)
    except ValidationError as exc:
        return Outcome(Action.DEAD_LETTER, retries, kind=ErrorKind.PERMANENT, error=_describe(exc))

    inline = iter(policy.inline_delays)
    while True:
        try:
            await handler(envelope)
            return Outcome(Action.ACK, retries)
        except Exception as exc:  # noqa: BLE001 - 所有异常都要分类处理，不能让消息卡住
            kind = classify(exc)
            delay = next(inline, None) if kind is ErrorKind.TRANSIENT else None
            if delay is not None:
                await sleep(delay)
                continue
            decision = policy.decide(kind, retries)
            if decision.action is Action.RETRY:
                return Outcome(Action.RETRY, retries + 1, decision.delay, kind, _describe(exc))
            return Outcome(Action.DEAD_LETTER, retries, kind=kind, error=_describe(exc))


# 单个消费进程同时处理的未确认消息上限：积压恢复时消息分批推送，而不是一次性全部压到进程内存
DEFAULT_PREFETCH = 20


def create_broker(amqp_url: str, prefetch: int = DEFAULT_PREFETCH):
    """消费进程使用的 broker。on_return_raises：mandatory 发布被退回时抛错，保证
    "重试/死信副本发布成功才 ack 原消息"在目标队列缺失时同样成立。"""
    from faststream.rabbit import Channel, RabbitBroker

    return RabbitBroker(amqp_url, default_channel=Channel(prefetch_count=prefetch, on_return_raises=True))


def subscribe(broker, queue: ConsumerQueue, handler: Handler, policy: RetryPolicy = DEFAULT_POLICY):
    """把 handler 注册为 queue 的消费者。队列由 topology 预先声明，这里只连接（passive）。"""
    from faststream.middlewares import AckPolicy
    from faststream.rabbit import RabbitMessage, RabbitQueue

    async def apply(message: RabbitMessage, outcome: Outcome) -> None:
        raw = message.raw_message
        if outcome.action is Action.ACK:
            await message.ack()
            return

        headers = {
            **(raw.headers or {}),
            RETRY_HEADER: outcome.retries,
            ERROR_KIND_HEADER: str(outcome.kind),
            ERROR_HEADER: outcome.error or "",
            ROUTING_KEY_HEADER: (raw.headers or {}).get(ROUTING_KEY_HEADER, raw.routing_key or ""),
        }
        if outcome.action is Action.RETRY:
            target = {"queue": queue.retry_queue(outcome.delay or 0)}
            log.warning(
                "消息 %s 处理失败（%s），%s 秒后第 %s 次重试：%s",
                message.message_id,
                outcome.kind,
                outcome.delay,
                outcome.retries,
                outcome.error,
            )
        else:
            target = {"exchange": DEAD_LETTER_EXCHANGE, "routing_key": queue.name}
            headers[FAILED_AT_HEADER] = now().isoformat()
            log.error(
                "消息 %s 进入死信队列 %s（%s，已重试 %s 次）：%s",
                message.message_id,
                queue.dead_letter_queue,
                outcome.kind,
                outcome.retries,
                outcome.error,
            )
        try:
            await broker.publish(
                raw.body,
                **target,
                headers=headers,
                message_id=message.message_id,
                content_type=raw.content_type or "application/json",
                content_encoding=raw.content_encoding,
                persist=True,
                mandatory=True,
            )
        except Exception:
            # 发布失败（通常是 broker 连接问题）：放回原队列，稍后由本消费者或其他实例再处理
            log.exception("消息 %s 的重试/死信副本发布失败，放回原队列", message.message_id)
            await asyncio.sleep(1)
            await message.nack(requeue=True)
            return
        await message.ack()

    async def raw_body(message: RabbitMessage) -> bytes:
        # 不让框架先按 JSON 解码：解码失败会发生在处理函数之外，消息既不 ack 也不进死信队列
        return message.body

    @broker.subscriber(
        RabbitQueue(queue.name, declare=False),
        ack_policy=AckPolicy.MANUAL,
        decoder=raw_body,
        title=f"consume:{queue.name}",
    )
    async def consume(body: bytes, message: RabbitMessage) -> None:
        outcome = await decide_outcome(message.body, message.headers, handler, policy)
        await apply(message, outcome)

    return consume


# ---------------- 消费进程：拓扑、健康检查与自愈 ----------------


@dataclass(frozen=True)
class TopologyCheck:
    missing: tuple[str, ...]  # 不存在的队列（topology.all_queue_names() 中的任意一个）
    idle: tuple[str, ...]  # 存在但没有消费者的消费队列

    def subscriptions_lost(self, own: set[str]) -> bool:
        """own 中的消费队列缺失或没有消费者：本进程的订阅已失效，需要重启进程重新订阅。"""
        return bool(set(self.idle) & own) or bool(set(self.missing) & own)


def check_topology(amqp_url: str, queues: tuple[ConsumerQueue, ...]) -> TopologyCheck:
    """检查拓扑中的全部队列是否存在，以及本进程负责的消费队列是否有消费者。"""
    from amqp.exceptions import NotFound
    from kombu import Connection

    from campus_common.topology import all_queue_names

    expected = all_queue_names()
    consumer_queues = {q.name for q in queues}

    missing, idle = [], []
    with Connection(amqp_url) as conn:
        for name in expected:
            channel = conn.channel()
            try:
                _, _, consumers = channel.queue_declare(name, passive=True)
                if name in consumer_queues and consumers == 0:
                    idle.append(name)
            except NotFound:
                missing.append(name)
            finally:
                if channel.is_open:
                    channel.close()
    return TopologyCheck(tuple(missing), tuple(idle))


def create_consumer_app(
    broker,
    amqp_url: str,
    queues: tuple[ConsumerQueue, ...],
    check_interval: float = 30,
):
    """消费进程的 ASGI 应用（uvicorn 启动）：

    - 启动前声明统一拓扑，订阅者只以 passive 方式连接；
    - GET /health：broker 连接可用且上一次自检正常时返回 204，供容器健康检查；
    - 自检：每 check_interval 秒检查拓扑。缺少重试、死信或未路由队列时重新声明拓扑；
      消费队列缺失或没有消费者（本进程的订阅已失效）时，重新声明拓扑后退出进程，
      由容器重启策略拉起并重新订阅。
    """
    import os
    import signal

    from faststream.asgi import AsgiFastStream, AsgiResponse, get

    from campus_common.topology import declare_topology_url

    state = {"healthy": True}

    @get(include_in_schema=False)
    async def health(scope) -> AsgiResponse:
        if not state["healthy"] or not await broker.ping(timeout=3):
            return AsgiResponse(b"", 500)
        return AsgiResponse(b"", 204)

    app = AsgiFastStream(broker, asgi_routes=[("/health", health)])

    @app.on_startup
    async def declare() -> None:
        await asyncio.to_thread(declare_topology_url, amqp_url)

    async def watchdog() -> None:
        own = {q.name for q in queues}
        while True:
            await asyncio.sleep(check_interval)
            try:
                result = await asyncio.to_thread(check_topology, amqp_url, queues)
            except Exception as exc:  # noqa: BLE001 - broker 暂时不可达时由连接自动恢复处理
                log.warning("消息拓扑自检失败：%s", exc)
                continue
            if result.missing:
                log.error("消息拓扑缺少队列：%s；重新声明", "、".join(result.missing))
                await asyncio.to_thread(declare_topology_url, amqp_url)
            if result.subscriptions_lost(own):
                state["healthy"] = False
                lost = sorted(own & (set(result.idle) | set(result.missing)))
                log.error("消费订阅已失效（%s），重启消费进程", "、".join(lost))
                os.kill(os.getpid(), signal.SIGTERM)
                return

    tasks: set[asyncio.Task] = set()

    @app.after_startup
    async def start_watchdog() -> None:
        task = asyncio.create_task(watchdog())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    return app
