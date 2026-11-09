"""M2 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed、clock）由 campus_common 的 pytest 插件提供。所有测试运行在冻结的
时钟上（pyproject 中 usefixtures = ["clock"]），默认时刻为 campus_common.testing.NOW（北京时间 06:00，
UTC 日期还是前一天）。需要更久的时间差时直接改库里的时间列，或把时刻作为参数传给定时任务。
"""

import asyncio
import sys
from datetime import timedelta

import pytest
from app import clients
from app.config import settings
from app.models import Outbox
from app.seed import seed_base
from campus_common.testing import NOW, record_service_calls, user_headers
from campus_common.timeutil import at_hour
from sqlalchemy import select

# psycopg 的异步连接在 Windows 上不支持默认的 ProactorEventLoop。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Docker Desktop 默认只将 PostgreSQL 映射到 IPv4；避免 localhost 先等待不可用的 ::1。
    settings.database_url = settings.database_url.replace("@localhost:", "@127.0.0.1:")

APPLICANT, DEPT_APPROVER, OTHER_DEPT_APPROVER, SCHOOL_APPROVER, FLOW_MANAGER = 1001, 2001, 2002, 3001, 4001

ROOM = {
    "id": 1,
    "building": "第三教学楼",
    "name": "H3106",
    "type": "classroom",
    "dept_id": None,
    "capacity": 60,
    "is_whole_bookable": True,
    "status": "enabled",
    "seats": [{"id": 11}],
    "open_hours": [{"weekday": day, "open_hour": 8, "close_hour": 22} for day in range(7)],
}
# M1 的查询教室、占用、释放、违约次数都成功（同一份响应包含各接口需要的字段）
M1_OK = ROOM | {"block_id": 9, "cancelled_reservations": [], "released": True, "count": 0}


def slot(days: int = 2, start_hour: int = 14, end_hour: int = 16) -> dict[str, str]:
    """今天之后第 days 天（业务时区）的整点时段。"""
    day = NOW.date() + timedelta(days=days)
    return {"start_at": at_hour(day, start_hour).isoformat(), "end_at": at_hour(day, end_hour).isoformat()}


def body(**overrides) -> dict:
    return {"room_id": 1, **slot(), "purpose": "班级读书会", "attendees": 30} | overrides


def headers(user_id: int, perms: list[str], dept_id: int | None = 1) -> dict[str, str]:
    return user_headers(settings, perms=perms, user_id=user_id, dept_id=dept_id)


@pytest.fixture
def as_applicant():
    return headers(APPLICANT, ["room:apply"])


@pytest.fixture
def as_dept_approver():
    return headers(DEPT_APPROVER, ["room:approve"])


@pytest.fixture
def as_other_dept_approver():
    return headers(OTHER_DEPT_APPROVER, ["room:approve"], dept_id=2)


@pytest.fixture
def as_school_approver():
    return headers(SCHOOL_APPROVER, ["room:approve_school"], dept_id=None)


@pytest.fixture
def as_flow_manager():
    return headers(FLOW_MANAGER, ["room:flow_manage"])


@pytest.fixture
def m1_calls(monkeypatch):
    return record_service_calls(monkeypatch, clients.m1, M1_OK)


def m1_room(monkeypatch, **changes) -> list:
    """M1 返回改过字段的教室；返回记录的调用。"""
    return record_service_calls(monkeypatch, clients.m1, M1_OK | changes)


def notifications(db, template: str) -> list[dict]:
    """outbox 中该模板的通知（NotificationSend 载荷）。"""
    db.expire_all()
    envelopes = db.scalars(select(Outbox.envelope).where(Outbox.type == "notification.send"))
    return [e["payload"] for e in envelopes if e["payload"]["template"] == template]


@pytest.fixture
def db_seed():
    return seed_base
