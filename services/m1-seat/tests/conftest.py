"""M1 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed）由 campus_common 的 pytest 插件提供。
"""

import pytest
from app.config import settings
from campus_common.testing import service_headers, user_headers

M2_KEY = "test-m2-key"
M3_KEY = "test-m3-key"
settings.service_keys = {"m2-room": M2_KEY, "m3-repair": M3_KEY}


@pytest.fixture
def as_student():
    return user_headers(settings, perms=["seat:reserve"])


@pytest.fixture
def as_m3():
    return service_headers("m3-repair", M3_KEY, idempotency_key="m3-order-7-block")
