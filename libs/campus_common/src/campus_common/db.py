"""数据库。

每个服务一个 schema（common / m1 / m2 / m3），只访问自己的 schema。
API 用异步会话，Celery worker 和 Alembic 用同步会话，驱动都是 psycopg 3，共用同一个 URL。

连接的会话时区设为业务时区：从数据库读出的 timestamptz 与 timeutil.now()/at_hour() 一样带 +08:00，
接口响应、消息与通知参数里的时间因此统一按业务时区序列化（表示的时刻不变）。
"""

from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import MetaData, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from campus_common.errors import AppError
from campus_common.timeutil import BIZ_TZ

CONNECT_ARGS = {"options": f"-c timezone={BIZ_TZ.key}"}

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def make_metadata(schema: str) -> MetaData:
    return MetaData(schema=schema, naming_convention=NAMING_CONVENTION)


def make_async_sessionmaker(url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url, pool_pre_ping=True, connect_args=CONNECT_ARGS)
    return async_sessionmaker(engine, expire_on_commit=False)


def make_sync_sessionmaker(url: str) -> sessionmaker[Session]:
    engine = create_engine(url, pool_pre_ping=True, connect_args=CONNECT_ARGS)
    return sessionmaker(engine, expire_on_commit=False)


def constraint_name(exc: IntegrityError) -> str | None:
    """违反的约束名（如 no_seat_overlap）；拿不到时返回 None。"""
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


@contextmanager
def constraint_errors(errors: Mapping[str, tuple[int, str, str]]) -> Iterator[None]:
    """把违反指定约束的 IntegrityError 转成 AppError(status, code, message)，其他 IntegrityError 原样抛出。

    with constraint_errors({"no_seat_overlap": (409, "SEAT_NOT_AVAILABLE", "座位已被预约")}):
        async with session.begin():
            ...
    """
    try:
        yield
    except IntegrityError as exc:
        error = errors.get(constraint_name(exc) or "")
        if error is None:
            raise
        raise AppError(*error) from exc


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
