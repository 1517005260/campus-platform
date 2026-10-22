from campus_common.scheduling import _lock_name, with_expiry
from celery import Celery
from celery.schedules import crontab


def lock_name_probe():
    return None


def test_lock_name_distinguishes_services_with_same_function():
    names = []
    for service in ("m1", "m2"):
        app = Celery(service)

        @app.task(name=f"{service}.relay_outbox")
        def relay_outbox():
            names.append(_lock_name(lock_name_probe))

        relay_outbox.apply()
    assert names == ["lock:task:m1.relay_outbox", "lock:task:m2.relay_outbox"]


def test_lock_name_outside_celery_uses_function_path():
    assert _lock_name(lock_name_probe) == f"lock:task:{__name__}.lock_name_probe"


def test_interval_tasks_expire_after_one_period():
    daily = crontab(hour=3, minute=0)
    schedule = with_expiry(
        {
            "relay": {"task": "m1.relay_outbox", "schedule": 2.0},
            "custom": {"task": "x", "schedule": 60.0, "options": {"expires": 5}},
            "daily": {"task": "y", "schedule": daily},
        }
    )
    assert schedule["relay"]["options"] == {"expires": 2.0}
    assert schedule["custom"]["options"] == {"expires": 5}
    assert "options" not in schedule["daily"]


def test_job_runs_without_lock_when_redis_unavailable():
    from campus_common.scheduling import singleton

    calls = []

    @singleton("redis://127.0.0.1:1/0")  # 没有 Redis 在监听
    def job():
        calls.append(1)
        return "done"

    assert job() == "done"
    assert calls == [1]
