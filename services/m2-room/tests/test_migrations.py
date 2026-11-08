"""数据迁移 0003：补显示信息、学校级审批改用 room:approve_school、规范化审批流名称。"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

pytestmark = pytest.mark.db

LEGACY_LEVELS = (
    '[{"level": 1, "approver_perm": "room:approve", "scope": "dept", "timeout_hours": 48},'
    ' {"level": 2, "approver_perm": "room:approve", "scope": "school", "timeout_hours": 24}]'
)


def test_0003_backfills_snapshots_and_moves_school_levels_to_school_permission(db):
    config = Config("alembic.ini")
    command.downgrade(config, "0002")
    try:
        db.execute(text("DELETE FROM m2.approval_flows"))
        db.execute(
            text(
                "INSERT INTO m2.approval_flows (id, name, priority, levels) VALUES "
                "(1, ' 默认 ', 0, CAST(:levels AS jsonb)), (2, '  ', 1, CAST(:levels AS jsonb))"
            ),
            {"levels": LEGACY_LEVELS},
        )
        db.execute(
            text(
                "INSERT INTO m2.applications (id, applicant_id, applicant_dept_id, room_id, start_at, "
                "end_at, purpose, attendees, status, flow_snapshot, current_level, deadline_at, version) "
                "VALUES "
                "(1, 1001, 1, 3, '2026-10-22 14:00+08', '2026-10-22 16:00+08', '读书会', 20, 'pending', "
                "CAST(:levels AS jsonb), 2, '2026-10-21 06:00+08', 2)"
            ),
            {"levels": LEGACY_LEVELS},
        )
        db.execute(
            text(
                "INSERT INTO m2.approval_records (application_id, level, approver_id, action, at) VALUES "
                "(1, 1, 2001, 'approve', now())"
            )
        )
        db.commit()

        command.upgrade(config, "0003")

        flows = db.execute(text("SELECT name, levels FROM m2.approval_flows ORDER BY id")).all()
        assert [name for name, _ in flows] == ["默认", "审批流 2"]
        expected_perms = ["room:approve", "room:approve_school"]
        assert [[lv["approver_perm"] for lv in levels] for _, levels in flows] == [expected_perms] * 2
        assert [lv["timeout_hours"] for lv in flows[0].levels] == [48, 24]
        application = db.execute(
            text("SELECT applicant_name, room_name, flow_snapshot FROM m2.applications")
        ).one()
        assert application.applicant_name == "用户1001"
        assert application.room_name == "教室 #3"
        assert [lv["approver_perm"] for lv in application.flow_snapshot] == expected_perms
        assert db.execute(text("SELECT approver_name FROM m2.approval_records")).scalar() == "用户2001"
    finally:
        db.rollback()
        command.upgrade(config, "head")
