"""服务间调用的错误转换：业务错误透传，服务之间的问题转成 502。"""

import httpx
import pytest
from campus_common.errors import AppError
from campus_common.service_client import ServiceClient
from campus_common.settings import ServiceSettings

SETTINGS = ServiceSettings(service_name="m2-room", db_schema="m2", database_url="postgresql://u@h/x_test")


async def call(monkeypatch, status, body):
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    with pytest.raises(AppError) as exc:
        await ServiceClient("http://m1", SETTINGS).request("GET", "/internal/v1/rooms/1")
    return exc.value


def error(code: str) -> dict:
    return {"code": code, "message": "m", "details": None, "request_id": None}


@pytest.mark.parametrize("status", [400, 404, 409])
async def test_business_errors_pass_through(monkeypatch, status):
    err = await call(monkeypatch, status, error("SEAT_NOT_AVAILABLE"))
    assert (err.status, err.code) == (status, "SEAT_NOT_AVAILABLE")


@pytest.mark.parametrize("status", [401, 403, 422, 500, 503])
async def test_inter_service_problems_become_502(monkeypatch, status):
    err = await call(monkeypatch, status, error("SERVICE_UNAUTHENTICATED"))
    assert (err.status, err.code) == (502, "UPSTREAM_ERROR")
    assert err.details == {"status": status, "code": "SERVICE_UNAUTHENTICATED"}


@pytest.mark.parametrize("body", [b"<html>bad gateway</html>", ["not", "an", "object"], {"no": "code"}])
async def test_unrecognised_error_body_becomes_502(monkeypatch, body):
    err = await call(monkeypatch, 404, body)
    assert (err.status, err.code) == (502, "UPSTREAM_ERROR")


async def test_network_failure_is_upstream_unavailable():
    with pytest.raises(AppError) as exc:
        await ServiceClient("http://127.0.0.1:1", SETTINGS).request("GET", "/x")
    assert (exc.value.status, exc.value.code) == (502, "UPSTREAM_UNAVAILABLE")
