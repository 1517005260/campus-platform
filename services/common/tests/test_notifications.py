"""站内通知（REQ-D-05）：只看自己的、未读筛选、最新在前、已读幂等、未读数、全部已读。"""

from datetime import timedelta

import pytest
from app.models import Notification
from campus_common.timeutil import now
from sqlalchemy import delete

from tests.conftest import headers_for

pytestmark = pytest.mark.db

STUDENT = headers_for(1, ["seat:reserve"])
OTHER = headers_for(2, ["seat:reserve"])


@pytest.fixture
def notes(db):
    """学生 1 的三条通知（时间从早到晚）和学生 2 的一条；去掉演示欢迎通知。"""
    db.execute(delete(Notification))
    base = now() - timedelta(hours=3)
    rows = [
        Notification(
            user_id=uid,
            template="t",
            title=title,
            content="",
            channels=["inapp"],
            created_at=base + timedelta(hours=h),
        )
        for uid, title, h in [(1, "最早", 0), (1, "中间", 1), (1, "最新", 2), (2, "别人的", 2)]
    ]
    db.add_all(rows)
    db.commit()
    return {n.title: n.id for n in rows}


def titles(client, headers, **query):
    return [
        n["title"] for n in client.get("/api/v1/notifications", params=query, headers=headers).json()["items"]
    ]


def test_list_only_own_newest_first(client, notes):
    assert titles(client, STUDENT) == ["最新", "中间", "最早"]
    assert titles(client, OTHER) == ["别人的"]
    page2 = client.get("/api/v1/notifications?size=2&page=2", headers=STUDENT).json()
    assert ([n["title"] for n in page2["items"]], page2["total"]) == (["最早"], 3)


def test_mark_read_is_idempotent_and_updates_filters(client, db, notes):
    assert client.post(f"/api/v1/notifications/{notes['中间']}/read", headers=STUDENT).status_code == 204
    first = db.get(Notification, notes["中间"]).read_at
    assert first is not None
    assert client.post(f"/api/v1/notifications/{notes['中间']}/read", headers=STUDENT).status_code == 204
    db.expire_all()
    assert db.get(Notification, notes["中间"]).read_at == first

    assert titles(client, STUDENT, unread="true") == ["最新", "最早"]
    assert titles(client, STUDENT, unread="false") == ["中间"]
    assert client.get("/api/v1/notifications/unread-count", headers=STUDENT).json() == {"count": 2}


def test_cannot_mark_someone_elses_notification(client, db, notes):
    resp = client.post(f"/api/v1/notifications/{notes['别人的']}/read", headers=STUDENT)
    assert (resp.status_code, resp.json()["code"]) == (404, "NOT_FOUND")
    assert db.get(Notification, notes["别人的"]).read_at is None


def test_mark_all_read_only_touches_own(client, db, notes):
    assert client.post("/api/v1/notifications/read-all", headers=STUDENT).status_code == 204
    assert client.get("/api/v1/notifications/unread-count", headers=STUDENT).json() == {"count": 0}
    assert client.get("/api/v1/notifications/unread-count", headers=OTHER).json() == {"count": 1}


def test_demo_users_start_with_one_welcome_notification(client, db):
    resp = client.get("/api/v1/notifications", headers=STUDENT).json()
    assert [n["template"] for n in resp["items"]] == ["common.welcome"]
    assert resp["items"][0]["created_at"].endswith("+08:00")


def test_requires_login(client, db):
    assert client.get("/api/v1/notifications").json()["code"] == "UNAUTHENTICATED"
