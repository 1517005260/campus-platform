"""统一分页：请求 ?page=1&size=20，响应 {items, total, page, size}。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


@dataclass
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
) -> PageParams:
    return PageParams(page=page, size=size)


def page_of[T](items: list[T], total: int, params: PageParams) -> Page[T]:
    return Page[T](items=items, total=total, page=params.page, size=params.size)


async def paginate[T](
    session: AsyncSession, stmt: Select[Any], params: PageParams, item: Callable[[Any], T]
) -> Page[T]:
    """执行查询的一页：total 按去掉排序的同一查询计数，items 按 stmt 的排序取第 page 页，
    每行经 item() 转成响应模型。

    查询单个实体时 item 收到该实体；查询多个实体或列时 item 收到一行（可按元组解包）。
    stmt 必须带确定的排序（例如以主键收尾），否则翻页可能重复或遗漏。

        await paginate(session, select(User).order_by(User.id), p, to_user)
        await paginate(session, select(Seat, Room).join(...).order_by(...), p, lambda row: to_item(*row))
    """
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    page = stmt.offset(params.offset).limit(params.size)
    if len(stmt.column_descriptions) == 1:
        rows = (await session.scalars(page)).all()
    else:
        rows = (await session.execute(page)).all()
    return page_of([item(row) for row in rows], total or 0, params)
