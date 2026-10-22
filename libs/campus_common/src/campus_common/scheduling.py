"""定时任务基础设施。

约定：定时任务一律"扫描数据库 + SKIP LOCKED 抢行 + 条件更新"，不给单条业务数据挂延时任务。
Beat 只负责按时投递扫描任务，每个服务只部署一个 Beat 实例。

singleton() 额外保证同一个扫描任务不会并发执行（例如上一轮还没跑完、或 Beat 被误启动了两个）。
锁失效时业务层的条件更新仍能兜底，所以这里的锁只是减少无效竞争，不是正确性的唯一保证。
"""

import functools
import logging
from collections.abc import Callable

import redis
from celery import Celery, current_task

from campus_common.settings import ServiceSettings

log = logging.getLogger(__name__)


def with_expiry(beat_schedule: dict) -> dict:
    """间隔型定时任务默认在一个周期后过期：worker 停机期间积压的扫描任务不会在恢复后集中执行，
    下一轮扫描本来就会处理全部到期数据。已显式设置 expires 或使用 crontab 的条目保持不变。"""
    result = {}
    for name, entry in beat_schedule.items():
        entry = dict(entry)
        schedule = entry.get("schedule")
        options = dict(entry.get("options", {}))
        if isinstance(schedule, int | float) and "expires" not in options:
            options["expires"] = float(schedule)
        if options:
            entry["options"] = options
        result[name] = entry
    return result


def create_celery(settings: ServiceSettings, beat_schedule: dict | None = None) -> Celery:
    app = Celery(settings.service_name, broker=settings.rabbitmq_url)
    app.conf.update(
        # 每个服务用自己的队列，避免 m1 的 worker 消费到 m2 的任务
        task_default_queue=settings.service_name,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_ignore_result=True,
        timezone="Asia/Shanghai",
        enable_utc=True,
        beat_schedule=with_expiry(beat_schedule or {}),
        broker_connection_retry_on_startup=True,
    )
    return app


def _lock_name(fn: Callable) -> str:
    # 锁名取 Celery 任务名（带服务前缀，如 m1.relay_outbox），各服务的同名任务各用一把锁；
    # 不在 Celery 任务中调用时（如测试）退回函数的模块路径
    task = current_task._get_current_object() if current_task else None
    name = task.name if task is not None and task.name else f"{fn.__module__}.{fn.__name__}"
    return f"lock:task:{name}"


def singleton(redis_url: str, ttl_seconds: int = 300) -> Callable:
    """同名任务同一时刻只运行一个；拿不到锁就跳过本轮。

    Redis 不可用时不加锁直接执行并告警：锁只用于减少无效竞争，正确性由业务层的条件更新保证，
    不能因为 Redis 故障让 outbox 投递和扫描任务全部停止。"""
    client = redis.Redis.from_url(redis_url)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            lock = client.lock(_lock_name(fn), timeout=ttl_seconds)
            try:
                acquired = lock.acquire(blocking=False)
            except redis.exceptions.RedisError as exc:
                log.warning("Redis 不可用，%s 本轮不加锁执行：%s", fn.__name__, exc)
                return fn(*args, **kwargs)
            if not acquired:
                log.info("跳过 %s：上一轮仍在运行", fn.__name__)
                return None
            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    lock.release()
                except redis.exceptions.RedisError:
                    pass  # 锁已过期被他人释放，或 Redis 暂时不可用

        return wrapper

    return decorator
