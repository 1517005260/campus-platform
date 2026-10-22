"""统一分页：请求 ?page=1&size=20，响应 {items, total, page, size}。"""

from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel


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
