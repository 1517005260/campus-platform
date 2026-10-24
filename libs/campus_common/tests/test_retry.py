import json

import pytest
from campus_common.retry import (
    Action,
    Decision,
    ErrorKind,
    PermanentError,
    RetryPolicy,
    TransientError,
    classify,
)
from campus_common.topology import RETRY_DELAYS
from pydantic import BaseModel, ValidationError
from sqlalchemy import exc as sa_exc


class M(BaseModel):
    x: int


def validation_error() -> ValidationError:
    try:
        M.model_validate({})
    except ValidationError as e:
        return e
    raise AssertionError


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (validation_error(), ErrorKind.PERMANENT),
        (json.JSONDecodeError("x", "", 0), ErrorKind.PERMANENT),
        (sa_exc.IntegrityError("insert", {}, Exception("fk")), ErrorKind.PERMANENT),
        (PermanentError("bad"), ErrorKind.PERMANENT),
        (sa_exc.OperationalError("select", {}, Exception("connection refused")), ErrorKind.TRANSIENT),
        (ConnectionRefusedError(), ErrorKind.TRANSIENT),
        (TimeoutError(), ErrorKind.TRANSIENT),
        (TransientError("busy"), ErrorKind.TRANSIENT),
        (RuntimeError("unexpected state"), ErrorKind.UNKNOWN),
        (KeyError("k"), ErrorKind.UNKNOWN),
    ],
)
def test_classify(exc, kind):
    assert classify(exc) is kind


def test_classify_follows_cause_chain():
    try:
        try:
            raise ConnectionResetError("db gone")
        except ConnectionResetError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert classify(outer) is ErrorKind.TRANSIENT


def test_classify_invalidated_connection_is_transient():
    e = sa_exc.DBAPIError("select", {}, Exception("x"), connection_invalidated=True)
    assert classify(e) is ErrorKind.TRANSIENT


def test_permanent_never_retried():
    assert RetryPolicy().decide(ErrorKind.PERMANENT, 0) == Decision(Action.DEAD_LETTER)


def test_transient_delays_escalate_then_repeat_last_tier():
    policy = RetryPolicy(max_transient_retries=8)
    delays = [policy.decide(ErrorKind.TRANSIENT, n).delay for n in range(8)]
    assert delays == [*RETRY_DELAYS, RETRY_DELAYS[-1], RETRY_DELAYS[-1], RETRY_DELAYS[-1]]


@pytest.mark.parametrize(("kind", "limit"), [(ErrorKind.TRANSIENT, 12), (ErrorKind.UNKNOWN, 3)])
def test_retry_limit_boundary(kind, limit):
    policy = RetryPolicy()
    assert policy.decide(kind, limit - 1).action is Action.RETRY
    assert policy.decide(kind, limit).action is Action.DEAD_LETTER


def test_policy_rejects_delay_without_retry_queue():
    with pytest.raises(ValueError, match="没有对应的重试队列"):
        RetryPolicy(delays=(5, 7))
