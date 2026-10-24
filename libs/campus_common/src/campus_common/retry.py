"""消费失败的分类与重试决策（纯逻辑，不依赖 RabbitMQ，便于测试）。

- 永久错误 PERMANENT：消息结构不合法、违反约束、业务抛 PermanentError。
  不重试，直接进死信队列。
- 临时错误 TRANSIENT：数据库/网络不可用、超时、死锁、业务抛 TransientError。
  先在进程内快速重试几次，仍失败则延迟重试（5s→30s→2m→10m→30m…），可覆盖数小时的故障。
- 未知错误 UNKNOWN：其他异常（多为代码缺陷）。
  少量延迟重试后进死信队列，修复后用 mqctl redrive 重放。

业务处理函数需要明确分类时，抛出 PermanentError 或 TransientError 即可。
"""

import enum
import json
import socket
from dataclasses import dataclass

import httpx
import psycopg
from pydantic import ValidationError
from sqlalchemy import exc as sa_exc

from campus_common.topology import RETRY_DELAYS


class PermanentError(Exception):
    """重试也不会成功的错误：消息直接进死信队列。"""


class TransientError(Exception):
    """依赖暂时不可用：稍后重试有望成功。"""


class ErrorKind(enum.StrEnum):
    PERMANENT = "permanent"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


_PERMANENT: tuple[type[BaseException], ...] = (
    PermanentError,
    ValidationError,
    json.JSONDecodeError,
    UnicodeDecodeError,
    sa_exc.IntegrityError,  # 外键、唯一约束：数据本身的问题
    sa_exc.DataError,  # 取值越界、格式错误
)

_TRANSIENT: tuple[type[BaseException], ...] = (
    TransientError,
    sa_exc.OperationalError,  # 连接失败、死锁、序列化冲突、数据库重启
    sa_exc.InterfaceError,
    sa_exc.DisconnectionError,
    sa_exc.TimeoutError,  # 连接池耗尽
    psycopg.OperationalError,
    ConnectionError,
    TimeoutError,
    socket.gaierror,  # 域名解析失败（如数据库容器重启中）
    httpx.TransportError,
)


def _classify_one(exc: BaseException) -> ErrorKind:
    if isinstance(exc, _PERMANENT):
        return ErrorKind.PERMANENT
    if isinstance(exc, _TRANSIENT):
        return ErrorKind.TRANSIENT
    if isinstance(exc, sa_exc.DBAPIError) and exc.connection_invalidated:
        return ErrorKind.TRANSIENT
    return ErrorKind.UNKNOWN


def classify(exc: BaseException) -> ErrorKind:
    """按异常本身分类；未知时沿 __cause__/__context__ 链查找被包装的原始异常。"""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        kind = _classify_one(current)
        if kind is not ErrorKind.UNKNOWN:
            return kind
        current = current.__cause__ or current.__context__
    return ErrorKind.UNKNOWN


class Action(enum.StrEnum):
    ACK = "ack"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class Decision:
    action: Action
    delay: int | None = None  # RETRY 时为重试队列的延迟档位（秒）


@dataclass(frozen=True)
class RetryPolicy:
    # 进程内快速重试的间隔（秒），只用于临时错误，抹平秒级抖动
    inline_delays: tuple[float, ...] = (0.2, 0.5, 1.0)
    # 延迟重试档位，必须是 topology.RETRY_DELAYS 中存在的值（对应的重试队列已声明）
    delays: tuple[int, ...] = RETRY_DELAYS
    # 延迟重试的最多次数：临时错误约覆盖 4 小时（5s+30s+2m+10m+30m×8），未知错误只试 3 次
    max_transient_retries: int = 12
    max_unknown_retries: int = 3

    def __post_init__(self) -> None:
        unknown = set(self.delays) - set(RETRY_DELAYS)
        if unknown:
            raise ValueError(f"重试延迟 {sorted(unknown)} 没有对应的重试队列（见 topology.RETRY_DELAYS）")

    def decide(self, kind: ErrorKind, retries_so_far: int) -> Decision:
        """retries_so_far：这条消息此前已经延迟重试过的次数（消息头 x-campus-retry）。"""
        if kind is ErrorKind.PERMANENT:
            return Decision(Action.DEAD_LETTER)
        limit = self.max_transient_retries if kind is ErrorKind.TRANSIENT else self.max_unknown_retries
        if retries_so_far >= limit:
            return Decision(Action.DEAD_LETTER)
        return Decision(Action.RETRY, self.delays[min(retries_so_far, len(self.delays) - 1)])


DEFAULT_POLICY = RetryPolicy()
