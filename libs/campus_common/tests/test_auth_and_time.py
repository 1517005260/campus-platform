from datetime import date

import pytest
import time_machine
from campus_common.auth import CurrentUser, create_token, decode_token
from campus_common.errors import AppError
from campus_common.settings import ServiceSettings
from campus_common.timeutil import at_hour

SETTINGS = ServiceSettings(
    service_name="t", db_schema="t", database_url="postgresql+psycopg://unused/x_test", jwt_ttl_minutes=60
)
USER = CurrentUser(id=1, username="u", name="n", dept_id=None, roles=["r"], perms=["seat:reserve"])


def test_token_roundtrip():
    assert decode_token(create_token(USER, SETTINGS), SETTINGS) == USER


def test_token_expires_after_ttl():
    with time_machine.travel("2026-10-20 08:00 +0800", tick=False):
        token = create_token(USER, SETTINGS)
    with time_machine.travel("2026-10-20 09:01 +0800", tick=False):
        with pytest.raises(AppError) as e:
            decode_token(token, SETTINGS)
    assert e.value.code == "TOKEN_EXPIRED"


def test_token_signed_with_other_secret_rejected():
    other = SETTINGS.model_copy(update={"jwt_secret": "x" * 40})
    with pytest.raises(AppError) as e:
        decode_token(create_token(USER, other), SETTINGS)
    assert e.value.code == "TOKEN_INVALID"


def test_at_hour_uses_business_timezone():
    assert at_hour(date(2026, 10, 20), 14).isoformat() == "2026-10-20T14:00:00+08:00"


def test_at_hour_24_is_next_midnight():
    assert at_hour(date(2026, 10, 31), 24).isoformat() == "2026-11-01T00:00:00+08:00"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "1", "username": "u", "typ": "user"},  # 缺少 name
        {"sub": "x", "username": "u", "name": "n", "typ": "user"},  # sub 不是数字
        {"sub": "1", "username": "u", "name": "n", "typ": "service"},  # 类型不是用户 token
        {"sub": "1", "username": "u", "name": "n"},  # 缺少类型
    ],
)
def test_signed_but_malformed_token_rejected(claims):
    import jwt as pyjwt

    token = pyjwt.encode({**claims, "exp": 4102444800}, SETTINGS.jwt_secret, algorithm="HS256")
    with pytest.raises(AppError) as exc:
        decode_token(token, SETTINGS)
    assert (exc.value.status, exc.value.code) == (401, "TOKEN_INVALID")
