"""统一错误格式：{code, message, details, request_id}。

业务代码抛 AppError，由这里注册的处理器转成统一响应。code 用大写下划线的业务错误码，
调用方（包括前端和其他服务）按 code 判断，不按 message 文本判断。
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from campus_common.context import request_id_var


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def not_found(what: str, id_: Any) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} {id_} 不存在")


def _response(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body = ErrorBody(code=code, message=message, details=details, request_id=request_id_var.get())
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{k: e[k] for k in ("loc", "msg", "type")} for e in exc.errors()]
        return _response(422, "VALIDATION_ERROR", "请求参数不合法", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return _response(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))


# 在 OpenAPI 中声明错误响应，便于调用方和契约检查看到
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorBody},
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
    502: {"model": ErrorBody},
}
