"""服务间 HTTP 调用。

- 自动带上本服务身份（X-Service-Name / X-Service-Key）和 X-Request-ID
- 写操作传 idempotency_key，失败重试是安全的
- 下游返回业务错误（400、404、409，统一错误格式）时原样转成 AppError，状态码与 code 不变，
  调用方可按 code 判断（例如 M1 的 SEAT_NOT_AVAILABLE）；
- 下游的认证失败（401/403）、参数校验失败（422）、5xx 或无法识别的错误体，说明是服务之间的问题，
  统一转成 502 UPSTREAM_ERROR，下游的状态码与 code 放在 details 中，不原样暴露给最终用户；
- 网络错误（连接失败、超时）转成 502 UPSTREAM_UNAVAILABLE。
"""

from typing import Any

import httpx

from campus_common.context import request_id_var
from campus_common.errors import AppError
from campus_common.settings import ServiceSettings


class ServiceClient:
    def __init__(self, base_url: str, settings: ServiceSettings, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._settings = settings
        self._timeout = timeout

    def _headers(self, idempotency_key: str | None) -> dict[str, str]:
        headers = {
            "X-Service-Name": self._settings.service_name,
            "X-Service-Key": self._settings.service_key,
        }
        if rid := request_id_var.get():
            headers["X-Request-ID"] = rid
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as c:
                resp = await c.request(
                    method, path, json=json, params=params, headers=self._headers(idempotency_key)
                )
        except httpx.HTTPError as e:
            raise AppError(502, "UPSTREAM_UNAVAILABLE", f"调用 {self._base_url} 失败") from e

        if resp.is_success:
            return resp.json() if resp.content else None
        raise _downstream_error(self._base_url, resp)


PASS_THROUGH_STATUSES = {400, 404, 409}


def _downstream_error(base_url: str, resp: httpx.Response) -> AppError:
    try:
        body = resp.json()
        code, message = body["code"], body["message"]
    except (ValueError, KeyError, TypeError):
        return AppError(502, "UPSTREAM_ERROR", f"下游 {base_url} 返回 {resp.status_code}")
    if resp.status_code in PASS_THROUGH_STATUSES:
        return AppError(resp.status_code, code, message, body.get("details"))
    return AppError(
        502,
        "UPSTREAM_ERROR",
        f"下游 {base_url} 拒绝了请求",
        {"status": resp.status_code, "code": code},
    )
