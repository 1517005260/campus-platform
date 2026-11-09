"""服务间 HTTP 调用。

- 自动带上本服务身份（X-Service-Name / X-Service-Key）和 X-Request-ID
- 写操作传 idempotency_key，失败重试是安全的
- 下游返回业务错误（400、404、409，统一错误格式）时原样转成 AppError，状态码与 code 不变，
  调用方可按 code 判断（例如 M1 的 SEAT_NOT_AVAILABLE）；
- 下游的认证失败（401/403）、参数校验失败（422）、5xx 或无法识别的错误体，说明是服务之间的问题，
  统一转成 502 UPSTREAM_ERROR，下游的状态码与 code 放在 details 中，不原样暴露给最终用户；
- 网络错误（连接失败、超时）转成 502 UPSTREAM_UNAVAILABLE。
502 的说明会显示给最终用户，只用服务的业务名称（如"M1 自习座位服务"），地址、端口和下游状态码只写日志。
"""

import logging
from typing import Any

import httpx

from campus_common.context import request_id_var
from campus_common.errors import AppError
from campus_common.settings import ServiceSettings

log = logging.getLogger(__name__)


class ServiceClient:
    def __init__(self, base_url: str, settings: ServiceSettings, service: str, timeout: float = 5.0):
        """service 是被调用服务面向用户的名称，用在 502 的说明里。"""
        self._base_url = base_url.rstrip("/")
        self._settings = settings
        self._service = service
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
            log.warning("调用 %s %s%s 失败：%r", method, self._base_url, path, e)
            raise AppError(502, "UPSTREAM_UNAVAILABLE", f"{self._service}暂不可用，请稍后再试") from e

        if resp.is_success:
            return resp.json() if resp.content else None
        error = self._downstream_error(resp)
        if error.status == 502:
            log.warning(
                "调用 %s %s%s 返回 %s：%s", method, self._base_url, path, resp.status_code, resp.text[:500]
            )
        raise error

    def _downstream_error(self, resp: httpx.Response) -> AppError:
        failed = f"{self._service}暂时无法处理该请求，请稍后再试"
        try:
            body = resp.json()
            code, message = body["code"], body["message"]
        except (ValueError, KeyError, TypeError):
            return AppError(502, "UPSTREAM_ERROR", failed)
        if resp.status_code in PASS_THROUGH_STATUSES:
            return AppError(resp.status_code, code, message, body.get("details"))
        return AppError(502, "UPSTREAM_ERROR", failed, {"status": resp.status_code, "code": code})


PASS_THROUGH_STATUSES = {400, 404, 409}
