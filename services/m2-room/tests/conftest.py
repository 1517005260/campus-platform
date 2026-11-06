"""M2 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed）由 campus_common 的 pytest 插件提供。
"""

import asyncio
import sys

import pytest
from app.config import settings
from app.seed import seed_base
from campus_common.testing import user_headers

# psycopg 的异步连接在 Windows 上不支持默认的 ProactorEventLoop。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Docker Desktop 默认只将 PostgreSQL 映射到 IPv4；避免 localhost 先等待不可用的 ::1。
    settings.database_url = settings.database_url.replace("@localhost:", "@127.0.0.1:")


@pytest.fixture
def as_applicant():
    return user_headers(settings, perms=["room:apply"])


@pytest.fixture
def as_approver():
    return user_headers(settings, perms=["room:approve"], user_id=2001)


@pytest.fixture
def as_flow_manager():
    return user_headers(settings, perms=["room:flow_manage"], user_id=3001)


@pytest.fixture
def db_seed():
    return seed_base
