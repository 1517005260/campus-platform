"""各服务 app/worker.py 的统一骨架：Celery 应用、同步会话、单例锁、outbox 投递与定时扫描任务。

    worker = ServiceWorker(settings, outbox_model=Outbox)   # 自动注册 <模块>.relay_outbox（每 2 秒）
    celery = worker.celery                                  # celery -A app.worker worker / beat

    worker.scan(jobs.mark_no_shows, every=60)               # 任务名 m1.mark_no_shows
    worker.scan(jobs.purge_inbox, cron=crontab(hour=3, minute=30))

扫描函数的签名统一为 fn(session, at) -> 处理的记录（列表）或条数：在一个事务里执行，at 为本轮的
当前时间（测试时直接传入）。同名任务同一时刻只运行一个（Redis 锁），间隔型任务在一个周期后过期。
"""

from collections.abc import Callable, Sized
from datetime import datetime

from celery.schedules import crontab as Crontab
from sqlalchemy.orm import Session

from campus_common.db import make_sync_sessionmaker
from campus_common.outbox import relay_outbox
from campus_common.publisher import EventPublisher
from campus_common.scheduling import create_celery, singleton, with_expiry
from campus_common.settings import ServiceSettings
from campus_common.timeutil import now

ScanFn = Callable[[Session, datetime], Sized | int]

RELAY_INTERVAL_SECONDS = 2.0


class ServiceWorker:
    def __init__(self, settings: ServiceSettings, *, outbox_model=None):
        self.settings = settings
        self.celery = create_celery(settings, beat_schedule={})
        self.sessions = make_sync_sessionmaker(settings.database_url)
        self._once = singleton(settings.redis_url)
        if outbox_model is not None:
            self._register_relay(outbox_model)

    def task_name(self, name: str) -> str:
        return f"{self.settings.module}.{name}"

    def scan(
        self, fn: ScanFn, *, every: float | None = None, cron: Crontab | None = None, name: str | None = None
    ):
        """把扫描函数注册为定时任务（every 秒一次，或按 cron），返回 Celery 任务。"""
        if (every is None) == (cron is None):
            raise ValueError("every 与 cron 必须且只能指定一个")
        task_name = self.task_name(name or fn.__name__)

        def run() -> int:
            with self.sessions() as session, session.begin():
                result = fn(session, now())
            return len(result) if isinstance(result, Sized) else int(result)

        run.__name__ = run.__qualname__ = fn.__name__
        task = self.celery.task(name=task_name)(self._once(run))
        self._schedule(task_name, every if every is not None else cron)
        return task

    def _register_relay(self, outbox_model) -> None:
        publisher = EventPublisher(self.settings.rabbitmq_url)
        task_name = self.task_name("relay_outbox")

        def relay() -> int:
            return relay_outbox(self.sessions, outbox_model, publisher)

        relay.__name__ = relay.__qualname__ = "relay_outbox"
        self.celery.task(name=task_name)(self._once(relay))
        self._schedule(task_name, RELAY_INTERVAL_SECONDS)

    def _schedule(self, task_name: str, schedule) -> None:
        entry = with_expiry({task_name: {"task": task_name, "schedule": schedule}})
        self.celery.conf.beat_schedule = {**(self.celery.conf.beat_schedule or {}), **entry}
