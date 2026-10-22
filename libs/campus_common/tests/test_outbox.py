"""relay_outbox 的批处理行为：单条消息自身出错时只跳过这一条，其他错误停止本批。"""

import uuid
from contextlib import contextmanager

import pytest
from amqp.exceptions import AccessRefused, MessageNacked
from campus_common import outbox
from kombu.exceptions import EncodeError, OperationalError


class Row:
    def __init__(self, n):
        self.id = uuid.uuid4()
        self.type = "notification.send"
        self.envelope = {"message_id": str(self.id), "n": n}
        self.attempts = 0
        self.published_at = None


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, _query):
        return self

    def all(self):
        return self.rows

    @contextmanager
    def begin(self):
        yield


def sessions_for(rows):
    @contextmanager
    def sessions():
        yield FakeSession(rows)

    return sessions


class Publisher:
    def __init__(self, fail):
        self.fail = fail  # n -> 异常
        self.published = []

    def publish(self, envelope, routing_key):
        if envelope["n"] in self.fail:
            raise self.fail[envelope["n"]]
        self.published.append(envelope["n"])


class _Query:
    """代替 SQLAlchemy 查询构造：任意链式调用都返回自身。"""

    def __getattr__(self, name):
        return lambda *a, **k: self


class Model:
    published_at = attempts = created_at = _Query()


@pytest.fixture(autouse=True)
def no_purge(monkeypatch):
    monkeypatch.setattr(outbox, "_purge_if_due", lambda sessions, model: None)
    monkeypatch.setattr(outbox, "select", lambda model: _Query())


@pytest.mark.parametrize("error", [KeyError("message_id"), EncodeError("not serializable")])
def test_message_error_skips_only_that_row(error):
    rows = [Row(1), Row(2), Row(3)]
    publisher = Publisher({2: error})
    assert outbox.relay_outbox(sessions_for(rows), Model, publisher) == 2
    assert publisher.published == [1, 3]
    assert [r.published_at is not None for r in rows] == [True, False, True]
    assert [r.attempts for r in rows] == [1, 1, 1]


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("connection refused"),
        AccessRefused("no access to exchange 'campus.events'"),
        MessageNacked(),
    ],
)
def test_broker_side_error_stops_batch(error):
    rows = [Row(1), Row(2), Row(3)]
    publisher = Publisher({2: error})
    assert outbox.relay_outbox(sessions_for(rows), Model, publisher) == 1
    assert publisher.published == [1]
    assert [r.attempts for r in rows] == [1, 1, 0]
