"""调用其他模块 /internal 接口的客户端（调用方使用）。

- 通信细节统一在这里：服务身份、X-Request-ID、超时、错误转换（ServiceClient）、幂等键格式、桩数据；
- 返回模型只声明调用方会用到的字段（宽容读取：提供方新增字段不影响调用方）；
- settings.stub_clients 为真时返回桩数据、不发网络请求，被调用方未完成时也能开发；
- 请求的路径、方法与字段由 tests/test_clients_contract.py 对照 contracts/openapi 校验，
  提供方改了接口会被发现。

各模块 app/clients.py 只写业务语义（例如 M2 的"占用教室" = 以 M2_OCCUPY 来源创建占用），通信交给这里。
"""

from campus_common.settings import ServiceSettings


def idempotency_key(settings: ServiceSettings, entity: str, entity_id: int | str, action: str) -> str:
    """服务间写操作的幂等键：<模块>-<实体>-<ID>-<动作>，例如 m3-order-7-block。"""
    return f"{settings.module}-{entity}-{entity_id}-{action}"
