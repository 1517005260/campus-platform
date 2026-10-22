"""部署本身：所有服务在线、版本与流水线部署的一致、内部接口不对外。"""

import os

import pytest

SERVICES = ["common", "m1", "m2", "m3"]


@pytest.mark.parametrize("svc", SERVICES)
def test_service_healthy(http, svc):
    assert http.get(f"/ops/{svc}/health").json() == {"status": "ok"}


@pytest.mark.parametrize("svc", SERVICES)
def test_running_expected_version(http, svc):
    expected = os.environ.get("EXPECTED_VERSION")
    if not expected:
        pytest.skip("未指定 EXPECTED_VERSION")
    assert http.get(f"/ops/{svc}/version").json()["version"] == expected


def test_internal_api_not_exposed(http):
    assert http.get("/internal/v1/rooms/1").status_code == 404


def test_login_token_accepted_by_every_service(http, login):
    headers = login("student")
    assert http.get("/api/v1/seat/rooms", headers=headers).status_code == 200
    assert http.get("/api/v1/room/applications/mine", headers=headers).status_code == 200
    assert http.get("/api/v1/repair/orders/mine", headers=headers).status_code == 200
