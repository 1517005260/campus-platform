import pytest
from app import mailer
from app.config import Settings

from tests.conftest import RecordingSMTP


@pytest.fixture(autouse=True)
def _smtp(fake_smtp):
    return fake_smtp


def settings(**overrides) -> Settings:
    return Settings(database_url="postgresql+psycopg://unused/x_test", **overrides)


def test_plain_smtp_without_auth():
    mailer.send_mail(settings(smtp_host="mailpit", smtp_port=1025), "a@x.cn", "标题", "正文")
    (smtp,) = RecordingSMTP.instances
    assert smtp.address == ("mailpit", 1025)
    assert smtp.calls == []
    assert RecordingSMTP.sent[0]["To"] == "a@x.cn"
    assert RecordingSMTP.sent[0]["Subject"] == "标题"


def test_starttls_with_login():
    s = settings(smtp_host="smtp.x.cn", smtp_port=587, smtp_security="starttls", smtp_username="u")
    mailer.send_mail(s, "a@x.cn", "t", "b")
    assert RecordingSMTP.instances[0].calls == ["starttls", "login:u"]


def test_disabled_when_host_empty():
    with pytest.raises(mailer.EmailDisabledError):
        mailer.send_mail(settings(smtp_host=""), "a@x.cn", "t", "b")
    assert RecordingSMTP.instances == []
