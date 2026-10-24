"""M3 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed）由 campus_common 的 pytest 插件提供。
"""

import pytest
from app.config import settings
from campus_common.testing import user_headers


@pytest.fixture
def as_reporter():
    return user_headers(settings, perms=["repair:report"])


@pytest.fixture
def as_worker():
    return user_headers(settings, perms=["repair:work"], user_id=3001)
