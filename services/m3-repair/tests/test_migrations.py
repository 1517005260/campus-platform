"""数据迁移：0003 区分代验收的时间线动作；0004 规范化保存时不校验的旧报修配置。"""

import pytest
from alembic import command
from alembic.config import Config
from app import schemas as s
from app.models import Setting, WorkOrder, WorkOrderEvent
from campus_common.params import load_params
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

pytestmark = pytest.mark.db

VALID_RULE = {"status": "dispatched", "timeout_hours": 24, "notify_perm": "repair:dispatch"}
REPORTER_ID, DISPATCHER_ID, MANAGER_ID = 1001, 2001, 4001


def _timeline(db) -> list[tuple[int, int, str]]:
    db.expire_all()
    rows = db.execute(
        select(WorkOrderEvent.order_id, WorkOrderEvent.actor_id, WorkOrderEvent.action).order_by(
            WorkOrderEvent.id
        )
    )
    return [tuple(row) for row in rows]


def _timeline_with_acceptor(order_id: int, acceptor_id: int, accept_action: str) -> list[tuple]:
    return [
        (order_id, REPORTER_ID, "report"),
        (order_id, DISPATCHER_ID, "dispatch"),
        (order_id, acceptor_id, accept_action),
    ]


def test_0003_marks_acceptance_by_someone_other_than_the_reporter_and_downgrade_restores(db):
    config = Config("alembic.ini")
    command.downgrade(config, "0002")
    try:
        for order_id, acceptor_id in ((1, REPORTER_ID), (2, MANAGER_ID)):
            db.add(
                WorkOrder(
                    id=order_id,
                    reporter_id=REPORTER_ID,
                    room_id=3,
                    category="空调",
                    description="不制冷",
                    photos=[],
                    status="closed",
                )
            )
            db.flush()
            db.add_all(
                WorkOrderEvent(order_id=order_id, actor_id=actor_id, action=action)
                for _, actor_id, action in _timeline_with_acceptor(order_id, acceptor_id, "accept")
            )
        db.commit()
        before = _timeline(db)

        command.upgrade(config, "0003")
        assert _timeline(db) == [
            *_timeline_with_acceptor(1, REPORTER_ID, "accept"),
            *_timeline_with_acceptor(2, MANAGER_ID, "admin_accept"),
        ]

        command.downgrade(config, "0002")
        assert _timeline(db) == before
    finally:
        command.upgrade(config, "head")


def _store_before_0004(db, stored: dict) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "0003")
    try:
        db.execute(insert(Setting).values([{"key": k, "value": v} for k, v in stored.items()]))
        db.commit()
    finally:
        command.upgrade(config, "head")
    db.expire_all()


def test_legacy_settings_are_normalized_to_the_nearest_valid_values(db):
    _store_before_0004(
        db,
        {
            "categories": [" 空调 ", "空调", "", "  ", "x" * 31, "x" * 30, "照明"],
            "admin_accept_after_hours": 0,
            "escalation_rules": [
                VALID_RULE,
                {"status": "in_progress", "timeout_hours": 72, "notify_perm": "管理员"},
                {"status": "pending_acceptance", "timeout_hours": 72, "notify_perm": "seat:stats"},
            ],
        },
    )

    assert load_params(db, Setting, s.RepairSettings) == s.RepairSettings(
        categories=["空调", "x" * 30, "照明"],
        admin_accept_after_hours=1,
        escalation_rules=[
            s.EscalationRule.model_validate(VALID_RULE),
            s.EscalationRule(status="in_progress", timeout_hours=72, notify_perm="repair:manage"),
            s.EscalationRule(status="pending_acceptance", timeout_hours=72, notify_perm="repair:manage"),
        ],
    )


def test_settings_with_no_usable_category_fall_back_to_defaults_and_valid_values_stay(db):
    _store_before_0004(
        db, {"categories": ["", "x" * 31], "admin_accept_after_hours": 5, "escalation_rules": [VALID_RULE]}
    )

    loaded = load_params(db, Setting, s.RepairSettings)

    assert loaded.categories == s.RepairSettings().categories
    assert (loaded.admin_accept_after_hours, loaded.escalation_rules) == (
        5,
        [s.EscalationRule.model_validate(VALID_RULE)],
    )
