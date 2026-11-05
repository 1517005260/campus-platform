"""邮件发送任务（REQ-D-06）：只发 email 通道、成功才标记、失败下一轮重试、未配置 SMTP 不发、并发不重复。

SMTP 由 tests.conftest.RecordingSMTP 代替（替换 smtplib.SMTP），
被测的 send_pending_emails 与 send_mail 原样运行。
"""

import smtplib
from datetime import timedelta

import pytest
from app import jobs
from app.config import settings
from app.models import Notification, User
from campus_common.db import make_sync_sessionmaker
from campus_common.timeutil import now
from sqlalchemy import select, update

from tests.conftest import REFUSED

pytestmark = pytest.mark.db

AT = now()


@pytest.fixture
def smtp(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    return fake_smtp


def add(db, user_id=1, channels=("inapp", "email"), age=timedelta(minutes=1), title="自习预约即将开始"):
    n = Notification(
        user_id=user_id,
        template="t",
        title=title,
        content="正文",
        channels=list(channels),
        created_at=AT - age,
    )
    db.add(n)
    db.commit()
    return n.id


def run(db):
    sent = jobs.send_pending_emails(db, AT)
    db.commit()
    return sent


def test_sends_email_once_and_marks_sent(db, smtp):
    nid = add(db)
    assert run(db) == [nid]
    (message,) = smtp.sent
    assert (message["To"], message["Subject"]) == ("student@campus.local", "自习预约即将开始")
    assert message.get_content().startswith("正文")
    assert db.get(Notification, nid).email_sent_at == AT
    assert run(db) == [] and len(smtp.sent) == 1


def test_inapp_only_notifications_not_emailed(db, smtp):
    add(db, channels=("inapp",))
    assert run(db) == [] and smtp.sent == []  # 演示欢迎通知也是 inapp


def test_nothing_sent_when_smtp_not_configured(db, fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    nid = add(db)
    assert run(db) == [] and fake_smtp.instances == []
    assert db.get(Notification, nid).email_sent_at is None


@pytest.mark.parametrize(
    "error",
    [
        REFUSED,
        smtplib.SMTPDataError(554, b"message rejected"),
        smtplib.SMTPNotSupportedError("SMTPUTF8 not supported"),
        UnicodeEncodeError("ascii", "张", 0, 1, "non-ascii address"),
    ],
)
def test_message_error_skips_only_that_message(db, smtp, error):
    bad, ok = add(db, user_id=1), add(db, user_id=2)
    smtp.fail = {"student@campus.local": error}
    assert run(db) == [ok]
    failed = db.get(Notification, bad)
    assert (failed.email_sent_at, failed.email_attempts) == (None, 1)
    assert type(error).__name__ in failed.email_last_error
    assert db.get(Notification, ok).email_attempts == 0


def test_failed_message_retried_until_attempt_limit(db, smtp):
    nid = add(db)
    smtp.fail = {"student@campus.local": smtplib.SMTPDataError(451, b"try later")}
    for attempt in range(1, jobs.MAX_EMAIL_ATTEMPTS + 1):
        assert run(db) == []
        assert db.get(Notification, nid).email_attempts == attempt
    smtp.fail = {}
    assert run(db) == []  # 达到上限后不再尝试
    assert smtp.sent == []


def test_failing_message_does_not_block_newer_ones(db, smtp, monkeypatch):
    monkeypatch.setattr(jobs, "BATCH", 1)
    bad, newer = add(db, user_id=1), add(db, user_id=2)
    smtp.fail = {"student@campus.local": smtplib.SMTPDataError(554, b"rejected")}
    assert run(db) == []  # 第一轮只轮到较早的那条，失败
    assert run(db) == [newer]  # 失败过的排到未尝试过的后面
    assert db.get(Notification, bad).email_attempts == 1


@pytest.mark.parametrize("error", [smtplib.SMTPServerDisconnected("closed"), TimeoutError("timed out")])
def test_server_error_while_sending_stops_round(db, smtp, error):
    first, second = add(db, user_id=1), add(db, user_id=2)
    smtp.fail = {"student@campus.local": error}
    assert run(db) == []  # 第二条也不在本轮发送
    assert db.get(Notification, first).email_attempts == 0
    smtp.fail = {}
    assert run(db) == [first, second]


def test_server_down_stops_round_without_counting_attempts(db, smtp):
    ids = [add(db, user_id=1), add(db, user_id=2)]
    smtp.down = True
    assert run(db) == []
    assert all(db.get(Notification, i).email_attempts == 0 for i in ids)
    smtp.down = False
    assert run(db) == ids


@pytest.mark.parametrize(("extra", "sent"), [(timedelta(0), True), (timedelta(seconds=1), False)])
def test_stale_notifications_not_emailed(db, smtp, extra, sent):
    nid = add(db, age=timedelta(hours=settings.email_max_age_hours) + extra)
    assert run(db) == ([nid] if sent else [])


def test_skips_users_disabled_or_without_email(db, smtp):
    db.execute(update(User).where(User.id == 1).values(active=False))
    db.execute(update(User).where(User.id == 2).values(email=None))
    db.commit()
    add(db, user_id=1), add(db, user_id=2)
    assert run(db) == []


def test_row_locked_by_another_worker_is_skipped(db, smtp):
    locked, free = add(db, user_id=1), add(db, user_id=2)
    other = make_sync_sessionmaker(settings.database_url)
    try:
        with other() as s, s.begin():
            s.scalar(select(Notification).where(Notification.id == locked).with_for_update())
            assert run(db) == [free]
        assert run(db) == [locked]
    finally:
        other.kw["bind"].dispose()
