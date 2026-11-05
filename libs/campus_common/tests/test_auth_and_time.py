from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
import time_machine
from campus_common.auth import CurrentUser, create_token, decode_token
from campus_common.db import constraint_errors, constraint_name
from campus_common.errors import AppError
from campus_common.settings import ServiceSettings
from campus_common.timeutil import TimeRangeModel, at_hour, to_biz
from sqlalchemy.exc import IntegrityError

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


def test_to_biz_moves_utc_evening_to_next_business_day():
    moment = datetime(2026, 10, 19, 23, 0, tzinfo=UTC)
    local = to_biz(moment)
    assert (local.date(), local.hour) == (date(2026, 10, 20), 7)
    assert local == moment


def test_to_biz_rejects_naive_datetime():
    with pytest.raises(ValueError):
        to_biz(datetime(2026, 10, 20, 7, 0))  # noqa: DTZ001


def test_constraint_name_reads_postgres_diagnostics():
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name="no_seat_overlap"))
    assert constraint_name(IntegrityError("INSERT ...", {}, orig)) == "no_seat_overlap"
    assert constraint_name(IntegrityError("INSERT ...", {}, Exception("no diag"))) is None


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


def test_constraint_errors_translates_only_listed_constraints():
    def violation(name: str) -> IntegrityError:
        return IntegrityError("INSERT ...", {}, SimpleNamespace(diag=SimpleNamespace(constraint_name=name)))

    errors = {"no_seat_overlap": (409, "SEAT_NOT_AVAILABLE", "座位已被预约")}
    with pytest.raises(AppError) as translated, constraint_errors(errors):
        raise violation("no_seat_overlap")
    assert (translated.value.status, translated.value.code) == (409, "SEAT_NOT_AVAILABLE")
    with pytest.raises(IntegrityError), constraint_errors(errors):
        raise violation("fk_other")


class _Span(TimeRangeModel):
    start_at: datetime
    end_at: datetime


class _OpenSpan(TimeRangeModel):
    start_at: datetime
    end_at: datetime | None = None


@pytest.mark.parametrize("model", [_Span, _OpenSpan])
def test_time_range_requires_end_after_start(model):
    start = at_hour(date(2026, 10, 20), 8)
    assert model(start_at=start, end_at=at_hour(date(2026, 10, 20), 9)).end_at > start
    for end in (start, at_hour(date(2026, 10, 20), 7)):
        with pytest.raises(ValueError, match="end_at 必须晚于 start_at"):
            model(start_at=start, end_at=end)


def test_open_ended_time_range_allows_missing_end():
    assert _OpenSpan(start_at=at_hour(date(2026, 10, 20), 8)).end_at is None
