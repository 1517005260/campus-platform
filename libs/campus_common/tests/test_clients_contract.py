"""跨模块客户端与提供方契约（contracts/openapi）的一致性。

逐个调用 campus_common.clients 中的方法（记录请求、不发网络），对照提供方导出的 OpenAPI 检查：
路径与方法存在、查询参数与请求体字段都已声明、必填字段都已发送、枚举取值一致、写接口带幂等键，
以及调用方读取模型的字段都在提供方的响应中。提供方修改 /internal 接口而调用方未跟进时，这里失败。
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import get_args

import pytest
from campus_common.clients.common import CommonClient, UserBrief, UserContact
from campus_common.clients.m1 import (
    BlockSource,
    M1BlockResult,
    M1Client,
    M1OpenHour,
    M1Reservation,
    M1Room,
)
from campus_common.settings import ServiceSettings
from campus_common.testing import record_service_calls
from pydantic import BaseModel

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "openapi"
T = datetime.fromisoformat("2026-10-20T14:00:00+08:00")
SETTINGS = ServiceSettings(service_name="m2-room", db_schema="m2", database_url="postgresql://u@h/x_test")


def load(service: str) -> dict:
    return json.loads((CONTRACTS / f"{service}.json").read_text())


def operation(spec: dict, method: str, path: str) -> dict:
    for template, ops in spec["paths"].items():
        if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), path) and method.lower() in ops:
            return ops[method.lower()]
    raise AssertionError(f"契约中没有 {method} {path}")


def resolve(spec: dict, schema: dict) -> dict:
    while "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    if schema.get("type") == "array":
        return resolve(spec, schema["items"])
    return schema


def response_schema(spec: dict, op: dict) -> dict:
    return resolve(spec, op["responses"]["200"]["content"]["application/json"]["schema"])


def assert_call_matches(spec: dict, call: tuple[str, str, dict]) -> dict:
    method, path, kwargs = call
    op = operation(spec, method, path)
    declared = {p["name"].lower(): p for p in op.get("parameters", [])}
    for name in kwargs.get("params") or {}:
        assert declared.get(name, {}).get("in") == "query", f"{method} {path} 未声明查询参数 {name}"
    if (header := declared.get("idempotency-key")) and header.get("required"):
        assert kwargs.get("idempotency_key"), f"{method} {path} 要求 Idempotency-Key"
    if body := kwargs.get("json"):
        schema = resolve(spec, op["requestBody"]["content"]["application/json"]["schema"])
        assert set(body) <= set(schema["properties"]), f"{path} 发送了未声明的字段"
        assert set(schema.get("required", [])) <= set(body), f"{path} 缺少必填字段"
    return op


def assert_reader_fields(spec: dict, op: dict, model: type[BaseModel]) -> None:
    assert_model_fields(spec, response_schema(spec, op), model)


def assert_model_fields(spec: dict, schema: dict, model: type[BaseModel]) -> None:
    """model 的字段都在提供方的 schema 中；嵌套模型（含列表元素）逐层核对。"""
    provided = schema["properties"]
    assert set(model.model_fields) <= set(provided), f"{model.__name__} 读取了提供方未返回的字段"
    for name, field in model.model_fields.items():
        nested = next((t for t in (field.annotation, *get_args(field.annotation)) if _is_model(t)), None)
        if nested is not None:
            assert_model_fields(spec, resolve(spec, provided[name]), nested)


def _is_model(tp: object) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


@pytest.fixture
def m1():
    return M1Client(SETTINGS.model_copy())


@pytest.fixture
def common():
    return CommonClient(SETTINGS.model_copy())


async def test_m1_room_query(monkeypatch, m1):
    calls = record_service_calls(monkeypatch, m1, _room())
    room = await m1.get_room(3)
    spec = load("m1-seat")
    assert_reader_fields(spec, assert_call_matches(spec, calls[0]), M1Room)
    assert room.open_hours == [
        M1OpenHour(weekday=0, open_hour=8, close_hour=22),
        M1OpenHour(weekday=5, open_hour=9, close_hour=17),
    ]
    assert [seat.id for seat in room.seats] == [31, 32]


def test_reader_check_covers_nested_models():
    """嵌套模型读取了提供方没有的字段时同样能发现（open_hours、seats 的元素）。"""

    class Renamed(BaseModel):
        weekday: int
        opens_at: int

    class Reader(BaseModel):
        open_hours: list[Renamed]

    spec = load("m1-seat")
    with pytest.raises(AssertionError, match="Renamed"):
        assert_reader_fields(spec, operation(spec, "GET", "/internal/v1/rooms/3"), Reader)


async def test_m1_block_create_and_release(monkeypatch, m1):
    calls = record_service_calls(
        monkeypatch, m1, {"block_id": 1, "cancelled_reservations": [], "released": True}
    )
    await m1.create_block(
        source="M2_OCCUPY", ref_id=42, room_id=3, start_at=T, end_at=T, reason="r", idempotency_key="k"
    )
    await m1.release_block("M2_OCCUPY", 42)
    spec = load("m1-seat")
    create = assert_call_matches(spec, calls[0])
    assert_call_matches(spec, calls[1])
    assert_reader_fields(spec, create, M1BlockResult)
    source = resolve(spec, create["requestBody"]["content"]["application/json"]["schema"])["properties"][
        "source"
    ]
    assert set(get_args(BlockSource)) == set(source["enum"])


async def test_m1_block_request_is_identical_for_the_same_instant_in_any_offset(monkeypatch, m1):
    """M1 按请求内容核对幂等键：同一时刻用不同时区表示时，发出的请求必须完全相同。"""
    calls = record_service_calls(monkeypatch, m1, {"block_id": 1, "cancelled_reservations": []})
    biz = datetime.fromisoformat("2026-10-20T06:00:00+08:00")
    utc = datetime.fromisoformat("2026-10-19T22:00:00+00:00")
    for start in (biz, utc):
        await m1.create_block(
            source="M3_MAINTENANCE",
            ref_id=7,
            room_id=3,
            start_at=start,
            end_at=start + timedelta(hours=2),
            reason="r",
            idempotency_key="m3-order-7-block",
        )
    assert calls[0][2] == calls[1][2]
    assert calls[0][2]["json"]["start_at"] == "2026-10-20T06:00:00+08:00"
    assert calls[0][2]["json"]["end_at"] == "2026-10-20T08:00:00+08:00"


async def test_m1_reservations_and_violations(monkeypatch, m1):
    calls = record_service_calls(monkeypatch, m1, [])
    await m1.room_reservations(3, T, T)
    spec = load("m1-seat")
    assert_reader_fields(spec, assert_call_matches(spec, calls[0]), M1Reservation)

    calls = record_service_calls(monkeypatch, m1, {"user_id": 1, "count": 0})
    await m1.violation_count(1, T)
    assert_call_matches(spec, calls[0])


async def test_common_user_queries(monkeypatch, common):
    calls = record_service_calls(monkeypatch, common, [])
    await common.users_with_perm("room:approve", dept_id=1)
    spec = load("common")
    assert_reader_fields(spec, assert_call_matches(spec, calls[0]), UserBrief)

    calls = record_service_calls(monkeypatch, common, _user())
    await common.get_user(1)
    assert_reader_fields(spec, assert_call_matches(spec, calls[0]), UserContact)


async def test_stub_mode_never_touches_network():
    settings = SETTINGS.model_copy(update={"stub_clients": True})
    m1, common = M1Client(settings), CommonClient(settings)

    async def forbidden(*args, **kwargs):
        raise AssertionError("桩模式下不应发出请求")

    m1._http.request = common._http.request = forbidden
    room = await m1.get_room(5)
    assert room.id == 5
    assert [(h.weekday, h.open_hour, h.close_hour) for h in room.open_hours] == [(d, 8, 22) for d in range(7)]
    block = await m1.create_block(
        source="M3_MAINTENANCE", ref_id=7, room_id=5, start_at=T, end_at=None, reason="r", idempotency_key="k"
    )
    assert block.block_id == 7
    assert await m1.release_block("M3_MAINTENANCE", 7) is True
    assert await common.users_with_perm("repair:work")


def _room() -> dict:
    return {
        "id": 3,
        "building": "b",
        "name": "n",
        "type": "classroom",
        "dept_id": None,
        "capacity": 10,
        "is_whole_bookable": True,
        "status": "enabled",
        "floor": 1,
        "is_study_room": True,
        "open_hours": [
            {"weekday": 0, "open_hour": 8, "close_hour": 22},
            {"weekday": 5, "open_hour": 9, "close_hour": 17},
        ],
        "seats": [
            {"id": 31, "room_id": 3, "code": "A-01", "outlet": "none", "status": "enabled"},
            {"id": 32, "room_id": 3, "code": "A-02", "outlet": "fixed", "status": "disabled"},
        ],
    }


def _user() -> dict:
    return {"id": 1, "username": "u", "name": "n", "dept_id": 1, "email": None}
