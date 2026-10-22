"""向 campus.events 发布消息（开启 publisher confirm）。

首次发布前声明全部消息拓扑（见 topology.py）：即使消费者从未启动过，消息也会进入已存在的
持久化队列；路由不到任何队列的消息由备用交换机收进 campus.events.unrouted，不会静默丢失。
发布失败后下一次发布会重新声明拓扑：broker 重启、队列被误删后自动恢复。broker 数据卷丢失时业务账号
也随之丢失，需要重新运行 mq-setup（部署环境中执行 docker compose up -d 即会重新运行）。
"""

from typing import Any

from kombu import Connection, Exchange
from kombu.exceptions import SerializationError

from campus_common.events import EXCHANGE
from campus_common.topology import declare_topology

# 只有这些错误由消息内容本身引起（信封无法序列化、缺少字段）；其余错误（连接中断、账号无权限、
# 交换机不存在、broker 拒绝确认）对同一批的每条消息都一样，应整批停止、稍后重试。
_MESSAGE_ERRORS = (SerializationError, KeyError, TypeError, ValueError)


def is_message_error(exc: BaseException) -> bool:
    """由单条消息自身引起、重试也不会好转的发布错误：只跳过这一条。"""
    return isinstance(exc, _MESSAGE_ERRORS)


class EventPublisher:
    def __init__(self, amqp_url: str):
        self._conn = Connection(amqp_url, transport_options={"confirm_publish": True})
        self._exchange = Exchange(EXCHANGE, type="topic", durable=True)
        self._declared = False

    def _ensure_topology(self) -> None:
        if not self._declared:
            self._conn.ensure_connection(max_retries=3)
            declare_topology(self._conn.default_channel)
            self._declared = True

    def publish(self, envelope: dict[str, Any], routing_key: str) -> None:
        try:
            self._ensure_topology()
            with self._conn.Producer() as producer:
                producer.publish(
                    envelope,
                    exchange=self._exchange,
                    routing_key=routing_key,
                    serializer="json",
                    delivery_mode=2,  # 持久化
                    message_id=str(envelope["message_id"]),
                    retry=True,
                    retry_policy={"max_retries": 3},
                )
        except Exception:
            self._declared = False
            raise

    def close(self) -> None:
        self._conn.release()
