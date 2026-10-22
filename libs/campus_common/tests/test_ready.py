from campus_common.app_factory import create_app
from campus_common.settings import ServiceSettings
from fastapi.testclient import TestClient


def test_ready_reports_unavailable_when_database_unreachable():
    settings = ServiceSettings(
        service_name="t", db_schema="t", database_url="postgresql+psycopg://u:p@127.0.0.1:1/x_test"
    )
    client = TestClient(create_app(settings, title="t", description="", routers=[]))
    assert client.get("/health").status_code == 200
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unavailable"
