"""M3 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed、clock）由 campus_common 的 pytest 插件提供。

所有测试运行在冻结的时钟上（插件的 clock fixture，pyproject 中 usefixtures 启用），默认时刻为
campus_common.testing.NOW。JWT 在冻结的时钟下签发，移动时钟不要超过 token 有效期（8 小时）；
需要更久的时间差时直接改库里的时间列，或把时刻作为参数传给定时任务。
"""

import pytest
from app import clients
from app.config import settings
from campus_common.testing import record_service_calls, user_headers

REPORTER_ID, DISPATCHER_ID, WORKER_ID, MANAGER_ID = 1001, 2001, 3001, 4001
WORKER = {"id": WORKER_ID, "username": "worker", "name": "王师傅", "dept_id": None}


@pytest.fixture
def as_reporter():
    return user_headers(settings, perms=["repair:report"], user_id=REPORTER_ID)


@pytest.fixture
def as_dispatcher():
    return user_headers(settings, perms=["repair:dispatch"], user_id=DISPATCHER_ID)


@pytest.fixture
def as_worker():
    return user_headers(settings, perms=["repair:work"], user_id=WORKER_ID)


@pytest.fixture
def as_manager():
    return user_headers(settings, perms=["repair:manage"], user_id=MANAGER_ID)


@pytest.fixture
def common_calls(monkeypatch):
    """common 中拥有 repair:work 的只有 WORKER（派单校验用）；返回记录的调用。"""
    return record_service_calls(monkeypatch, clients.common, [WORKER])


@pytest.fixture
def m1_calls(monkeypatch):
    """M1 的查询教室、下架、释放都成功（同一份响应包含各接口需要的字段）；返回记录的调用。"""
    return record_service_calls(monkeypatch, clients.m1, M1_OK)


ROOM = {
    "id": 3,
    "building": "第三教学楼",
    "name": "H3106",
    "type": "classroom",
    "dept_id": None,
    "capacity": 60,
    "is_whole_bookable": True,
    "status": "enabled",
}
M1_OK = ROOM | {"block_id": 1, "cancelled_reservations": [], "released": True}
