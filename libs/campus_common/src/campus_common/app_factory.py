"""FastAPI 应用工厂：各服务的 main.py 都通过 create_app() 创建应用，保证行为一致。

统一提供：错误格式、X-Request-ID 透传、GET /health（存活）、GET /ready（就绪：数据库可用）、GET /version。
容器健康检查用 /ready，worker/beat 等依赖它的进程在数据库可用后才启动。

/ready 使用独立的、不复用连接的 engine：超时被取消的连接直接丢弃，不会回到业务连接池。
"""

import asyncio
import uuid

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from campus_common.context import request_id_var
from campus_common.db import make_async_sessionmaker
from campus_common.errors import register_error_handlers
from campus_common.settings import ServiceSettings

READY_TIMEOUT_SECONDS = 3


class VersionInfo(BaseModel):
    service: str
    version: str
    git_sha: str
    env: str


def create_app(
    settings: ServiceSettings,
    *,
    title: str,
    description: str,
    routers: list[APIRouter],
) -> FastAPI:
    app = FastAPI(title=title, description=description, version=settings.app_version)
    app.state.settings = settings
    app.state.sessionmaker = make_async_sessionmaker(settings.database_url)
    probe_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": READY_TIMEOUT_SECONDS},
    )

    register_error_handlers(app)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    @app.get("/health", tags=["ops"], summary="存活检查")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"], summary="就绪检查：数据库可用")
    async def ready() -> JSONResponse:
        try:
            async with asyncio.timeout(READY_TIMEOUT_SECONDS), probe_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - 任何失败都表示未就绪
            return JSONResponse({"status": "unavailable", "reason": type(exc).__name__}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/version", tags=["ops"], summary="当前运行版本", response_model=VersionInfo)
    async def version() -> VersionInfo:
        return VersionInfo(
            service=settings.service_name,
            version=settings.app_version,
            git_sha=settings.git_sha,
            env=settings.deploy_env,
        )

    for router in routers:
        app.include_router(router)
    return app
