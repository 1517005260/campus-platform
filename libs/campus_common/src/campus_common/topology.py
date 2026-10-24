"""消息拓扑：exchange、队列、绑定、重试队列、死信队列和备用交换机的唯一定义。

所有进程启动时声明同一份拓扑（声明是幂等的）：
- 部署时一次性容器 mq-setup 以管理员账号执行 `python -m campus_common.mqctl setup`：
  声明拓扑、设置 policy、创建业务账号；其他服务在它成功退出后才启动；
- 生产者（EventPublisher）首次发布前、消费者启动前也各声明一次，任何启动顺序都不会丢消息。

    campus.events (topic) ──notification.send──► common.notification.send ──► 消费者
         │  │                                        │ 临时错误            │ 永久错误/重试耗尽
         │  └─m1.# m2.# m3.#──► campus.events.domain   ▼                      ▼
         │      （领域事件存档，保留 7 天）     <队列>.retry.<N>s (TTL)    campus.events.dlx (direct)
         │  路由不到（policy: alternate-exchange）过期后经默认交换机回到原队列   ▼
         ▼                                                            campus.dlq.<队列>
    campus.events.unrouted (fanout) → campus.events.unrouted 队列（非空即有消息类型缺少队列）

注意：队列和交换机的参数一经创建不能修改，重复声明时参数不同会被 RabbitMQ 拒绝（406）。
- 需要调整的行为（如备用交换机）用 policy 设置，见 policies()；
- 重试延迟写在队列名里（.retry.30s），调整延迟档位就是使用另一组队列，不需要修改队列参数。
"""

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from dataclasses import dataclass

from campus_common.events import DEAD_LETTER_EXCHANGE, EXCHANGE

log = logging.getLogger(__name__)

UNROUTED_EXCHANGE = "campus.events.unrouted"
UNROUTED_QUEUE = "campus.events.unrouted"

# 领域事件存档：m1/m2/m3 的状态变化事件目前没有必需的消费者（供统计和 DSH 代理订阅），
# 统一进入存档队列，按时间与条数滚动淘汰，便于排查；同时让未路由队列只反映配置遗漏。
DOMAIN_ARCHIVE_QUEUE = "campus.events.domain"
DOMAIN_EVENT_KEYS: tuple[str, ...] = ("m1.#", "m2.#", "m3.#")
DOMAIN_ARCHIVE_ARGUMENTS = {
    "x-queue-type": "classic",
    "x-message-ttl": 7 * 24 * 3600 * 1000,
    "x-max-length": 100_000,
    "x-overflow": "drop-head",
}

# 重试延迟档位（秒）。第 n 次重试使用第 min(n, 档位数) 档，最后一档重复使用。
RETRY_DELAYS: tuple[int, ...] = (5, 30, 120, 600, 1800)

# 消息头：已重试次数、失败分类与原因（死信与重试消息上都有，便于排查和重放）
RETRY_HEADER = "x-campus-retry"
ERROR_KIND_HEADER = "x-campus-error-kind"
ERROR_HEADER = "x-campus-error"
ROUTING_KEY_HEADER = "x-campus-routing-key"
FAILED_AT_HEADER = "x-campus-failed-at"

CLASSIC = {"x-queue-type": "classic"}


@dataclass(frozen=True)
class ConsumerQueue:
    """一个消费队列：绑定 campus.events 上的若干路由键，自带重试队列和死信队列。"""

    name: str
    routing_keys: tuple[str, ...]

    @property
    def arguments(self) -> dict:
        # 安全网：消费者异常退出等情况下被 reject 的消息仍进入死信队列
        return {
            **CLASSIC,
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
            "x-dead-letter-routing-key": self.name,
        }

    @property
    def dead_letter_queue(self) -> str:
        return f"campus.dlq.{self.name}"

    def retry_queue(self, delay: int) -> str:
        return f"{self.name}.retry.{delay}s"

    def retry_queue_arguments(self, delay: int) -> dict:
        # 消息在重试队列中等待 delay 秒，过期后经默认交换机直接回到原队列，
        # 不经过 campus.events，因此不会被同一路由键的其他订阅方重复收到
        return {
            **CLASSIC,
            "x-message-ttl": delay * 1000,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": self.name,
        }


NOTIFICATION_QUEUE = ConsumerQueue("common.notification.send", ("notification.send",))
AUDIT_QUEUE = ConsumerQueue("common.audit.record", ("audit.record",))

# 新增消费队列只需在这里登记，所有进程下次启动时自动创建
CONSUMER_QUEUES: tuple[ConsumerQueue, ...] = (NOTIFICATION_QUEUE, AUDIT_QUEUE)


def consumer_queue(name: str) -> ConsumerQueue:
    for q in CONSUMER_QUEUES:
        if q.name == name:
            return q
    raise KeyError(f"未登记的消费队列：{name}")


def declare_topology(channel) -> None:
    """在给定的 AMQP 通道上声明全部拓扑。channel 为 kombu/py-amqp 通道，可重复执行。"""
    channel.exchange_declare(EXCHANGE, "topic", durable=True, auto_delete=False)
    channel.exchange_declare(DEAD_LETTER_EXCHANGE, "direct", durable=True, auto_delete=False)
    channel.exchange_declare(UNROUTED_EXCHANGE, "fanout", durable=True, auto_delete=False)

    channel.queue_declare(UNROUTED_QUEUE, durable=True, auto_delete=False, arguments=dict(CLASSIC))
    channel.queue_bind(UNROUTED_QUEUE, UNROUTED_EXCHANGE, routing_key="")

    channel.queue_declare(
        DOMAIN_ARCHIVE_QUEUE, durable=True, auto_delete=False, arguments=dict(DOMAIN_ARCHIVE_ARGUMENTS)
    )
    for key in DOMAIN_EVENT_KEYS:
        channel.queue_bind(DOMAIN_ARCHIVE_QUEUE, EXCHANGE, routing_key=key)

    for q in CONSUMER_QUEUES:
        channel.queue_declare(q.name, durable=True, auto_delete=False, arguments=q.arguments)
        for key in q.routing_keys:
            channel.queue_bind(q.name, EXCHANGE, routing_key=key)

        channel.queue_declare(q.dead_letter_queue, durable=True, auto_delete=False, arguments=dict(CLASSIC))
        channel.queue_bind(q.dead_letter_queue, DEAD_LETTER_EXCHANGE, routing_key=q.name)

        for delay in RETRY_DELAYS:
            channel.queue_declare(
                q.retry_queue(delay),
                durable=True,
                auto_delete=False,
                arguments=q.retry_queue_arguments(delay),
            )


def declare_topology_url(amqp_url: str) -> None:
    from kombu import Connection

    with Connection(amqp_url) as conn:
        declare_topology(conn.default_channel)


# ---------------- policy（通过 RabbitMQ 管理接口设置） ----------------


def policies() -> dict[str, dict]:
    """需要用 policy 设置的行为。policy 可随时修改，不受"参数不可变"限制。"""
    return {
        "campus-events-unrouted": {
            "pattern": f"^{re.escape(EXCHANGE)}$",
            "apply-to": "exchanges",
            "priority": 10,
            "definition": {"alternate-exchange": UNROUTED_EXCHANGE},
        },
    }


def management_target(amqp_url: str, management_url: str | None = None) -> tuple[str, str, str, str]:
    """从 AMQP 地址推出管理接口地址、vhost 与账号：返回 (base_url, vhost, user, password)。"""
    parsed = urllib.parse.urlparse(amqp_url)
    vhost = urllib.parse.unquote(parsed.path[1:]) if len(parsed.path) > 1 else "/"
    base = (management_url or f"http://{parsed.hostname}:15672").rstrip("/")
    return (
        base,
        vhost,
        urllib.parse.unquote(parsed.username or "guest"),
        urllib.parse.unquote(parsed.password or "guest"),
    )


# 业务账号可声明（configure）的资源：本拓扑（campus.*、common.*）与各服务的 Celery 资源
# （任务队列同服务名；celeryev 事件；pidbox 控制与应答队列）。删除其他资源会被 broker 拒绝。
SERVICE_NAMES = ("common", "m1-seat", "m2-room", "m3-repair")
APP_CONFIGURE_PATTERN = (
    r"^(campus\..+|common\..+|"
    + "|".join(re.escape(name) for name in SERVICE_NAMES)
    + r"|celeryev(\..+)?|celery\.pidbox|reply\.celery\.pidbox|.+\.celery\.pidbox|.+\.reply\.celery\.pidbox)$"
)


@dataclass(frozen=True)
class AppAccount:
    """业务进程使用的账号：无管理标签，不能管理用户与 policy；只能声明 APP_CONFIGURE_PATTERN
    范围内的资源，可读写本 vhost。"""

    username: str
    password: str


def _management_put(base: str, path: str, body: dict, auth: str, timeout: float) -> None:
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode(),
        method="PUT",
        headers={"Content-Type": "application/json", "Authorization": auth},
    )
    with urllib.request.urlopen(req, timeout=timeout):  # noqa: S310 - 地址来自配置
        pass


def apply_management(
    amqp_url: str,
    management_url: str | None = None,
    app_account: AppAccount | None = None,
    timeout: float = 5,
) -> None:
    """通过管理接口设置 policy，并创建/更新业务账号。amqp_url 必须是管理员账号。"""
    base, vhost, user, password = management_target(amqp_url, management_url)
    auth = "Basic " + b64encode(f"{user}:{password}".encode()).decode()
    vhost_q = urllib.parse.quote(vhost, safe="")
    for name, body in policies().items():
        _management_put(base, f"/api/policies/{vhost_q}/{name}", body, auth, timeout)
    if app_account is not None:
        name_q = urllib.parse.quote(app_account.username, safe="")
        _management_put(
            base, f"/api/users/{name_q}", {"password": app_account.password, "tags": ""}, auth, timeout
        )
        _management_put(
            base,
            f"/api/permissions/{vhost_q}/{name_q}",
            {"configure": APP_CONFIGURE_PATTERN, "write": ".*", "read": ".*"},
            auth,
            timeout,
        )


def setup(
    amqp_url: str,
    management_url: str | None = None,
    app_account: AppAccount | None = None,
    wait_seconds: float = 60,
    interval: float = 2,
) -> None:
    """声明拓扑、设置 policy、准备业务账号。RabbitMQ 刚启动时管理接口可能晚于 AMQP 就绪，期间重试。"""
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            declare_topology_url(amqp_url)
            apply_management(amqp_url, management_url, app_account)
            return
        except Exception as exc:
            # 参数冲突（406）、账号或权限错误属于配置问题，重试没有意义，立即失败
            if _is_config_error(exc) or time.monotonic() >= deadline:
                raise
            log.warning("消息拓扑初始化失败，%s 秒后重试：%s", interval, exc)
            time.sleep(interval)


def _is_config_error(exc: Exception) -> bool:
    from amqp.exceptions import AccessRefused, NotAllowed, PreconditionFailed

    if isinstance(exc, PreconditionFailed | AccessRefused | NotAllowed):
        return True
    return isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500


def all_queue_names() -> list[str]:
    """拓扑中声明的全部队列。"""
    names = [UNROUTED_QUEUE, DOMAIN_ARCHIVE_QUEUE]
    for q in CONSUMER_QUEUES:
        names += [q.name, q.dead_letter_queue, *(q.retry_queue(d) for d in RETRY_DELAYS)]
    return names
