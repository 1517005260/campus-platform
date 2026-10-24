import json
import re

from campus_common import topology
from campus_common.events import DEAD_LETTER_EXCHANGE, EXCHANGE
from campus_common.topology import (
    APP_CONFIGURE_PATTERN,
    AUDIT_QUEUE,
    CONSUMER_QUEUES,
    DOMAIN_ARCHIVE_QUEUE,
    NOTIFICATION_QUEUE,
    RETRY_DELAYS,
    UNROUTED_EXCHANGE,
    UNROUTED_QUEUE,
    AppAccount,
    all_queue_names,
    apply_management,
    declare_topology,
    management_target,
    policies,
)


class RecordingChannel:
    def __init__(self):
        self.exchanges, self.queues, self.bindings = {}, {}, set()

    def exchange_declare(self, name, type_, durable, auto_delete):
        self.exchanges[name] = type_

    def queue_declare(self, name, durable, auto_delete, arguments):
        assert durable
        self.queues[name] = arguments

    def queue_bind(self, queue, exchange, routing_key):
        self.bindings.add((exchange, routing_key, queue))


def declared() -> RecordingChannel:
    ch = RecordingChannel()
    declare_topology(ch)
    return ch


def test_consumer_queues_bound_and_dead_lettered():
    ch = declared()
    assert (EXCHANGE, "notification.send", NOTIFICATION_QUEUE.name) in ch.bindings
    assert (EXCHANGE, "audit.record", AUDIT_QUEUE.name) in ch.bindings
    for q in CONSUMER_QUEUES:
        # 所有进程都会声明这些队列，参数必须与这里完全一致，否则 RabbitMQ 拒绝声明（406）
        assert ch.queues[q.name] == {
            "x-queue-type": "classic",
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
            "x-dead-letter-routing-key": q.name,
        }
        assert (DEAD_LETTER_EXCHANGE, q.name, q.dead_letter_queue) in ch.bindings


def test_retry_queues_return_to_origin_queue_after_ttl():
    ch = declared()
    for q in CONSUMER_QUEUES:
        for delay in RETRY_DELAYS:
            args = ch.queues[q.retry_queue(delay)]
            assert args["x-message-ttl"] == delay * 1000
            # 经默认交换机直接回原队列，不经过 campus.events（其他订阅方不会重复收到）
            assert (args["x-dead-letter-exchange"], args["x-dead-letter-routing-key"]) == ("", q.name)
        assert not any(b[2] == q.retry_queue(RETRY_DELAYS[0]) for b in ch.bindings)


def test_unrouted_messages_are_kept():
    ch = declared()
    assert ch.exchanges[UNROUTED_EXCHANGE] == "fanout"
    assert (UNROUTED_EXCHANGE, "", UNROUTED_QUEUE) in ch.bindings
    policy = policies()["campus-events-unrouted"]
    assert policy["definition"] == {"alternate-exchange": UNROUTED_EXCHANGE}
    assert policy["apply-to"] == "exchanges"
    assert policy["pattern"] == r"^campus\.events$"


def test_management_target_from_amqp_url():
    assert management_target("amqp://campus:p%40ss@rabbitmq:5672//") == (
        "http://rabbitmq:15672",
        "/",
        "campus",
        "p@ss",
    )
    assert management_target("amqp://u:p@h:5672/campus", "http://mgmt:15672/")[:2] == (
        "http://mgmt:15672",
        "campus",
    )


def test_management_sets_policy_and_limited_app_account(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout):
        calls.append((req.get_method(), req.full_url, json.loads(req.data)))
        return Response()

    monkeypatch.setattr(topology.urllib.request, "urlopen", urlopen)
    apply_management("amqp://campus:pw@rabbitmq:5672//", app_account=AppAccount("campus_app", "s3"))
    by_url = {url: body for _, url, body in calls}
    assert by_url["http://rabbitmq:15672/api/policies/%2F/campus-events-unrouted"]["definition"] == {
        "alternate-exchange": UNROUTED_EXCHANGE
    }
    # 业务账号没有任何管理标签，只有本 vhost 的读写配置权限
    assert by_url["http://rabbitmq:15672/api/users/campus_app"] == {"password": "s3", "tags": ""}
    assert by_url["http://rabbitmq:15672/api/permissions/%2F/campus_app"] == {
        "configure": APP_CONFIGURE_PATTERN,
        "write": ".*",
        "read": ".*",
    }
    assert all(method == "PUT" for method, _, _ in calls)


def test_domain_events_archived_with_bounded_retention():
    ch = declared()
    for key in ("m1.#", "m2.#", "m3.#"):
        assert (EXCHANGE, key, DOMAIN_ARCHIVE_QUEUE) in ch.bindings
    args = ch.queues[DOMAIN_ARCHIVE_QUEUE]
    assert args["x-message-ttl"] == 7 * 24 * 3600 * 1000
    assert (args["x-max-length"], args["x-overflow"]) == (100_000, "drop-head")
    # 存档队列不接收通知与审计，它们只进各自的消费队列
    assert not any(
        k in ("notification.send", "audit.record") for _, k, q in ch.bindings if q == DOMAIN_ARCHIVE_QUEUE
    )


def test_all_queue_names_match_declared_queues():
    assert sorted(all_queue_names()) == sorted(declared().queues)


def test_app_account_may_configure_only_platform_resources():
    allowed = re.compile(APP_CONFIGURE_PATTERN)
    for name in [*declared().queues, *declared().exchanges]:
        assert allowed.match(name), name
    for name in [
        "m1-seat",
        "celeryev",
        "celeryev.3f2a",
        "celery.pidbox",
        "reply.celery.pidbox",
        "worker@a1b2.celery.pidbox",
        "6c1e.reply.celery.pidbox",
    ]:
        assert allowed.match(name), name
    for name in ["other-app", "amq.direct", "m1-seat-x", "campus", "celery"]:
        assert not allowed.match(name), name
