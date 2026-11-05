"""common 测试的特有 fixture。

通用 fixture（client、migrated、db、db_seed）由 campus_common 的 pytest 插件提供。
"""

import smtplib

import pytest
from app import mailer
from app.config import settings
from app.permissions import PERMISSIONS
from app.seed import BOOTSTRAP_ADMIN, seed_base, seed_demo
from campus_common.testing import user_headers

M2_KEY = "test-m2-key"
settings.service_keys = {"m2-room": M2_KEY}


@pytest.fixture
def db_seed():
    """默认基于完整的种子（基础 + 演示），与部署后的环境一致。"""

    def seed(session) -> None:
        seed_base(session)
        seed_demo(session)

    return seed


def headers_for(user_id: int, perms: list[str]) -> dict[str, str]:
    """以指定用户 ID 和权限码发请求（不经过登录）。"""
    return user_headers(settings, perms=perms, user_id=user_id)


@pytest.fixture
def admin():
    """引导管理员（拥有全部权限码）的请求头。"""
    return headers_for(BOOTSTRAP_ADMIN.id, list(PERMISSIONS))


def login(client, username: str, password: str = "campus123"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


class RecordingSMTP:
    """替代 smtplib.SMTP：记录连接与发出的邮件。fail 把收件人映射到发送这封信时抛出的异常，
    down=True 时连接失败。"""

    instances: list["RecordingSMTP"] = []
    sent: list = []
    fail: dict[str, Exception] = {}
    down = False

    def __init__(self, host, port, timeout):
        if RecordingSMTP.down:
            raise ConnectionRefusedError("SMTP 不可用")
        self.address = (host, port)
        self.calls: list[str] = []
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
        error = RecordingSMTP.fail.get(message["To"])
        if error is not None:
            raise error
        RecordingSMTP.sent.append(message)


REFUSED = smtplib.SMTPRecipientsRefused({"x": (550, b"no such user")})


@pytest.fixture
def fake_smtp(monkeypatch):
    RecordingSMTP.instances, RecordingSMTP.sent, RecordingSMTP.fail, RecordingSMTP.down = [], [], {}, False
    monkeypatch.setattr(mailer.smtplib, "SMTP", RecordingSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", RecordingSMTP)
    return RecordingSMTP
