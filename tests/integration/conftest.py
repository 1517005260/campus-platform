"""跨模块集成测试：对部署好的环境（经网关）发真实 HTTP 请求。

由流水线在每次测试环境部署后运行：scripts/integration_test.sh <网关地址> [期望版本]
依赖测试环境的演示账号（SEED_DEMO=true），密码默认 campus123。
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
PASSWORD = os.environ.get("DEMO_PASSWORD", "campus123")


@pytest.fixture(scope="session")
def http():
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="session")
def login(http):
    cache: dict[str, dict[str, str]] = {}

    def _login(username: str) -> dict[str, str]:
        if username not in cache:
            resp = http.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
            resp.raise_for_status()
            cache[username] = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        return cache[username]

    return _login
