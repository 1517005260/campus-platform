"""消息运维命令。RABBITMQ_URL 默认取环境变量（与服务配置一致）。

    python -m campus_common.mqctl setup                     # 声明拓扑、设置 policy、创建业务账号
                                                            #（部署时由一次性容器 mq-setup 执行）
    python -m campus_common.mqctl status                    # 各队列积压、重试中、死信、未路由消息数
    python -m campus_common.mqctl redrive common.notification.send [--limit N] [--include-permanent]
    python -m campus_common.mqctl replay-unrouted [--limit N]

redrive：把死信队列中的消息放回原队列重新处理（重试计数清零）。默认跳过永久错误
（结构不合法的消息放回去只会再次失败），它们被移到死信队列末尾。每次最多处理执行时
队列里已有的条数，重放后再次失败的消息不会在同一次执行中被反复搬运。
replay-unrouted：把 campus.events.unrouted 中的消息按原路由键重新发布到 campus.events，
用于新增消费队列后，重新投递此前没有队列接收的消息。
"""

import argparse
import os
import sys

from kombu import Connection

from campus_common.events import DEAD_LETTER_EXCHANGE, EXCHANGE
from campus_common.retry import ErrorKind
from campus_common.topology import (
    CONSUMER_QUEUES,
    DOMAIN_ARCHIVE_QUEUE,
    ERROR_KIND_HEADER,
    RETRY_DELAYS,
    RETRY_HEADER,
    UNROUTED_QUEUE,
    AppAccount,
    consumer_queue,
    declare_topology,
    setup,
)

DEFAULT_URL = "amqp://campus:campus@localhost:5672//"


def _depth(channel, name: str) -> tuple[int, int]:
    _, messages, consumers = channel.queue_declare(name, passive=True)
    return messages, consumers


def status(conn: Connection) -> list[tuple[str, int, int]]:
    channel = conn.default_channel
    rows = []
    for q in CONSUMER_QUEUES:
        rows.append((q.name, *_depth(channel, q.name)))
        for delay in RETRY_DELAYS:
            rows.append((q.retry_queue(delay), *_depth(channel, q.retry_queue(delay))))
        rows.append((q.dead_letter_queue, *_depth(channel, q.dead_letter_queue)))
    rows.append((UNROUTED_QUEUE, *_depth(channel, UNROUTED_QUEUE)))
    rows.append((DOMAIN_ARCHIVE_QUEUE, *_depth(channel, DOMAIN_ARCHIVE_QUEUE)))
    return rows


def _move(conn: Connection, source: str, limit: int | None, route) -> tuple[int, int]:
    """从 source 取出最多 limit 条（且不超过当前条数），route(message) 返回 (exchange, routing_key,
    headers, moved)。先确认发布再 ack，保证不丢。"""
    channel = conn.default_channel
    count = _depth(channel, source)[0]
    total = count if limit is None else min(limit, count)
    producer = conn.Producer(channel=channel)
    moved = skipped = 0
    for _ in range(total):
        message = channel.basic_get(source, no_ack=False)
        if message is None:
            break
        exchange, routing_key, headers, is_moved = route(message)
        props = message.properties
        producer.publish(
            message.body,
            exchange=exchange,
            routing_key=routing_key,
            headers=headers,
            content_type=props.get("content_type", "application/json"),
            content_encoding=props.get("content_encoding", "utf-8"),
            message_id=props.get("message_id"),
            delivery_mode=2,
            mandatory=True,
        )
        channel.basic_ack(message.delivery_info["delivery_tag"])
        moved += is_moved
        skipped += not is_moved
    return moved, skipped


def redrive(conn: Connection, queue_name: str, limit: int | None, include_permanent: bool) -> tuple[int, int]:
    q = consumer_queue(queue_name)

    def route(message):
        headers = dict(message.properties.get("application_headers") or {})
        permanent = headers.get(ERROR_KIND_HEADER) == ErrorKind.PERMANENT
        if permanent and not include_permanent:
            return DEAD_LETTER_EXCHANGE, q.name, headers, False  # 移到死信队列末尾
        headers[RETRY_HEADER] = 0
        return "", q.name, headers, True  # 经默认交换机直接回到原队列

    return _move(conn, q.dead_letter_queue, limit, route)


def replay_unrouted(conn: Connection, limit: int | None) -> tuple[int, int]:
    def route(message):
        headers = dict(message.properties.get("application_headers") or {})
        return EXCHANGE, message.delivery_info["routing_key"], headers, True

    return _move(conn, UNROUTED_QUEUE, limit, route)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m campus_common.mqctl", description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=os.environ.get("RABBITMQ_URL", DEFAULT_URL))
    parser.add_argument(
        "--management-url",
        default=os.environ.get("RABBITMQ_MANAGEMENT_URL"),
        help="默认 http://<RabbitMQ 主机>:15672",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_setup = sub.add_parser("setup", help="声明拓扑并设置 policy")
    p_setup.add_argument("--wait", type=float, default=60, help="等待 RabbitMQ 就绪的最长秒数")
    p_setup.add_argument(
        "--app-user",
        default=os.environ.get("RABBITMQ_APP_USER"),
        help="创建/更新的业务账号（密码取环境变量 RABBITMQ_APP_PASSWORD）；不填则不创建",
    )
    sub.add_parser("status", help="查看队列积压")
    p_redrive = sub.add_parser("redrive", help="把死信放回原队列")
    p_redrive.add_argument("queue", choices=[q.name for q in CONSUMER_QUEUES])
    p_redrive.add_argument("--limit", type=int)
    p_redrive.add_argument("--include-permanent", action="store_true")
    p_replay = sub.add_parser("replay-unrouted", help="重新发布未路由的消息")
    p_replay.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.cmd == "setup":
        account = None
        if args.app_user:
            password = os.environ.get("RABBITMQ_APP_PASSWORD")
            if not password:
                parser.error("指定了业务账号但未设置 RABBITMQ_APP_PASSWORD")
            account = AppAccount(args.app_user, password)
        setup(args.url, args.management_url, account, wait_seconds=args.wait)
        print("消息拓扑与 policy 已就绪")
        return 0

    with Connection(args.url, transport_options={"confirm_publish": True}) as conn:
        declare_topology(conn.default_channel)
        if args.cmd == "status":
            print(f"{'队列':<48}{'消息':>8}{'消费者':>8}")
            for name, messages, consumers in status(conn):
                print(f"{name:<48}{messages:>8}{consumers:>8}")
        elif args.cmd == "redrive":
            moved, skipped = redrive(conn, args.queue, args.limit, args.include_permanent)
            print(f"已放回原队列 {moved} 条；跳过永久错误 {skipped} 条（仍在死信队列）")
        else:
            moved, _ = replay_unrouted(conn, args.limit)
            print(f"已重新发布 {moved} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
