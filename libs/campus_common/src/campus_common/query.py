"""查询参数依赖。"""

import inspect
from collections.abc import Callable
from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError


def query_model[M: BaseModel](model: type[M]) -> Callable[..., M]:
    """把 Pydantic 模型的字段作为查询参数的依赖，可与分页等其他查询参数一起使用：

        slot: Annotated[HourRange, Depends(query_model(HourRange))]

    模型自身的校验（包括 model_validator 的跨字段校验）失败时与请求体一样返回 422 VALIDATION_ERROR。
    FastAPI 只在模型是唯一的查询参数时才展开 Annotated[Model, Query()]，因此需要这个依赖。"""

    def dependency(**values: Any) -> M:
        try:
            return model(**values)
        except ValidationError as exc:
            raise RequestValidationError(
                [{**error, "loc": ("query", *error["loc"])} for error in exc.errors(include_url=False)]
            ) from exc

    dependency.__signature__ = inspect.signature(model)  # type: ignore[attr-defined]
    return dependency
