"""请求上下文。X-Request-ID 由网关生成，各服务透传给下游 HTTP 调用和消息。"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
