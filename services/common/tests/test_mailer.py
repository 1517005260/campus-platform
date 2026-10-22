import pytest
from app import mailer
from app.config import Settings


class RecordingSMTP:
    instances: list["RecordingSMTP"] = []

    def __init__(self, host, port, timeout):
        self.address = (host, port)
        self.calls: list[str] = []
        self.sent = []
        RecordingSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}")

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    RecordingSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", RecordingSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", RecordingSMTP)


def settings(**overrides) -> Settings:
    return Settings(database_url="postgresql+psycopg://unused/x_test", **overrides)


def test_plain_smtp_without_auth():
    mailer.send_mail(settings(smtp_host="mailpit", smtp_port=1025), "a@x.cn", "标题", "正文")
    (smtp,) = RecordingSMTP.instances
    assert smtp.address == ("mailpit", 1025)
    assert smtp.calls == []
    assert smtp.sent[0]["To"] == "a@x.cn"
    assert smtp.sent[0]["Subject"] == "标题"


def test_starttls_with_login():
    s = settings(smtp_host="smtp.x.cn", smtp_port=587, smtp_security="starttls", smtp_username="u")
    mailer.send_mail(s, "a@x.cn", "t", "b")
    assert RecordingSMTP.instances[0].calls == ["starttls", "login:u"]


def test_disabled_when_host_empty():
    with pytest.raises(mailer.EmailDisabledError):
        mailer.send_mail(settings(smtp_host=""), "a@x.cn", "t", "b")
    assert RecordingSMTP.instances == []
