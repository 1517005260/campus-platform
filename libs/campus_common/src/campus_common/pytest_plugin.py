"""pytest 插件（通过 entry point 自动加载）：服务测试的通用 fixture 与测试库保护。

fixture（在服务目录下运行测试时使用，按约定导入 app.config.settings 与 app.main.app）：
- client：FastAPI TestClient；
- migrated：会话级，迁移到最新版本；
- db：每个测试从空的服务 schema 开始（清空全部业务表），再执行 db_seed，返回同步会话；
- db_seed：默认不写数据，服务需要预置数据时在 conftest.py 中覆盖，返回 fn(session)。

测试库保护：测试只允许连接名称以 _test 结尾的数据库。

- 在服务目录（含 alembic.ini）运行时，整个测试会话开始前检查，覆盖所有可能访问数据库的测试；
- 在其他目录运行时，只检查标记了 db 或使用 db/migrated fixture 的测试。

各服务的 db fixture 会 TRUNCATE 本服务 schema，而服务配置的 DATABASE_URL 默认值指向开发库，
因此测试必须显式连接测试库。本地用 `make test svc=...`（连接 campus_test），CI 的临时 Postgres
也命名为 campus_test。
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DB_SUFFIX = "_test"
DB_FIXTURES = {"db", "migrated"}


def database_url_problem(url: str | None) -> str | None:
    """返回拒绝的原因；允许时返回 None。"""
    if not url:
        return "未设置 DATABASE_URL（服务默认值指向开发库）"
    name = make_url(url).database or ""
    if not name.endswith(TEST_DB_SUFFIX):
        return f"DATABASE_URL 指向数据库 {name!r}，测试只允许连接名称以 {TEST_DB_SUFFIX} 结尾的库"
    return None


def _exit(problem: str) -> None:
    pytest.exit(
        f"{problem}。测试会清空表，请使用 `make test svc=<服务>`（连接 campus_test），"
        "或把 DATABASE_URL 指向名称以 _test 结尾的库",
        returncode=4,
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    if (Path(session.config.rootpath) / "alembic.ini").exists():
        problem = database_url_problem(os.environ.get("DATABASE_URL"))
        if problem:
            _exit(problem)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    needs_db = item.get_closest_marker("db") is not None or DB_FIXTURES & set(
        getattr(item, "fixturenames", ())
    )
    if not needs_db:
        return
    problem = database_url_problem(os.environ.get("DATABASE_URL"))
    if problem:
        _exit(problem)


# ---------------- 通用 fixture ----------------


@pytest.fixture
def client():
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="session")
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def db_seed() -> Callable[[Session], None]:
    return lambda session: None


@pytest.fixture
def db(migrated, db_seed) -> Iterator[Session]:
    from app.config import settings

    from campus_common.db import make_sync_sessionmaker
    from campus_common.testing import truncate_schema

    sessions = make_sync_sessionmaker(settings.database_url)
    try:
        with sessions() as session:
            truncate_schema(session, settings.db_schema)
            db_seed(session)
            session.commit()
            yield session
    finally:
        sessions.kw["bind"].dispose()
