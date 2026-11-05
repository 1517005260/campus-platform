"""M1 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed、clock）由 campus_common 的 pytest 插件提供。

所有测试运行在冻结的时钟上（插件的 clock fixture，pyproject 中 usefixtures 启用）：默认时刻
campus_common.testing.NOW 是 DAY（周二）北京时间 06:00，此时 UTC 日期还是前一天，时区换算错误会直接暴露。
需要其他时刻时用 clock.move_to(...)；JWT 在冻结的时钟下签发，移动时钟不能早于 NOW，
也不要超过 token 有效期（8 小时）。
"""

import pytest
from app.config import settings
from campus_common.testing import NOW, service_headers, user_headers

DAY = NOW.date()

M2_KEY = "test-m2-key"
M3_KEY = "test-m3-key"
settings.service_keys = {"m2-room": M2_KEY, "m3-repair": M3_KEY}


@pytest.fixture
def as_student():
    return user_headers(settings, perms=["seat:reserve"])


@pytest.fixture
def as_m2():
    return service_headers("m2-room", M2_KEY, idempotency_key="m2-app-7-occupy")


@pytest.fixture
def as_room_admin():
    return user_headers(settings, perms=["seat:room_manage"], dept_id=1)


@pytest.fixture
def as_screen():
    return user_headers(settings, perms=["seat:checkin_code"], dept_id=1)


@pytest.fixture
def as_config():
    return user_headers(settings, perms=["seat:config"], dept_id=1)


@pytest.fixture
def as_stats():
    return user_headers(settings, perms=["seat:stats"], dept_id=1)


@pytest.fixture
def as_m3():
    return service_headers("m3-repair", M3_KEY, idempotency_key="m3-order-7-block")
