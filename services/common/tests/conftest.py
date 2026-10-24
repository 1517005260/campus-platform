"""common 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed）由 campus_common 的 pytest 插件提供。
"""

import pytest
from app.config import settings
from app.seed import seed_base, seed_demo

M2_KEY = "test-m2-key"
settings.service_keys = {"m2-room": M2_KEY}


@pytest.fixture
def db_seed():
    """common 的测试都基于权限码、预置角色与演示账号。"""

    def seed(session) -> None:
        seed_base(session)
        seed_demo(session)

    return seed
