"""ServiceWorker：任务命名、调度表、事务与返回值约定。"""

from contextlib import contextmanager
from datetime import datetime

import pytest
from campus_common import worker as worker_module
from campus_common.settings import ServiceSettings
from campus_common.worker import ServiceWorker
from celery.schedules import crontab

SETTINGS = ServiceSettings(service_name="m1-seat", db_schema="m1", database_url="postgresql://u@h/x_test")


class Outbox:
    pass


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(worker_module, "singleton", lambda url: lambda fn: fn)
    return ServiceWorker(SETTINGS, outbox_model=Outbox)


def test_relay_and_scans_are_named_by_module_and_scheduled(worker):
    def mark_no_shows(session, at):
        return []

    def purge(session, at):
        return 0

    worker.scan(mark_no_shows, every=60)
    worker.scan(purge, cron=crontab(hour=3, minute=0))
    schedule = worker.celery.conf.beat_schedule
    assert schedule["m1.relay_outbox"]["schedule"] == 2.0
    assert schedule["m1.mark_no_shows"] == {
        "task": "m1.mark_no_shows",
        "schedule": 60,
        "options": {"expires": 60.0},
    }
    assert "options" not in schedule["m1.purge"]
    assert {"m1.relay_outbox", "m1.mark_no_shows", "m1.purge"} <= set(worker.celery.tasks)


def test_scan_runs_in_one_transaction_with_current_time(worker, monkeypatch):
    events = []

    class Session:
        @contextmanager
        def begin(self):
            events.append("begin")
            yield
            events.append("commit")

    @contextmanager
    def sessions():
        yield Session()

    worker.sessions = sessions
    fixed = datetime.fromisoformat("2026-10-20T08:15:00+08:00")
    monkeypatch.setattr(worker_module, "now", lambda: fixed)

    def job(session, at):
        events.append(("job", at))
        return [1, 2, 3]

    task = worker.scan(job, every=60)
    assert task.run() == 3
    assert events == ["begin", ("job", fixed), "commit"]


def test_scan_requires_exactly_one_schedule(worker):
    def job(session, at):
        return 0

    with pytest.raises(ValueError):
        worker.scan(job)
    with pytest.raises(ValueError):
        worker.scan(job, every=1, cron=crontab())


def test_module_code_from_service_name():
    assert [
        ServiceSettings(service_name=n, db_schema="x", database_url="postgresql://u@h/x_test").module
        for n in ("common", "m1-seat", "m2-room", "m3-repair")
    ] == ["common", "m1", "m2", "m3"]
