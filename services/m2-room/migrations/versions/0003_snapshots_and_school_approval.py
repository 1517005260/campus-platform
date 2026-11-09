"""display snapshots, occupy attempts, school-level approval permission

结构（先扩展：新列可空或带默认值，回滚到上一版镜像仍能写入）：
- applications：applicant_username / applicant_name / room_name（提交时的显示信息快照，读接口与通知不再调用
  common、M1）；occupy_requested_at（最近一次请求 M1 占用的时间，用于释放残留占用）。
- approval_records：approver_username / approver_name / approver_dept_id（动作发生时的操作人信息）。

数据：
- 已有申请与记录没有快照，显示名补为"用户<ID>"、教室补为"教室 #<ID>"。
- 学校级审批改用 room:approve_school：审批流配置与申请快照中每一级的 approver_perm 按 scope 改写
  （dept → room:approve，school → room:approve_school），在途申请的第 2 级由学校级审批人处理；
  审批流名称去掉首尾空白，空白名称改为"审批流 <ID>"（之后保存接口按同一规则校验）；规范化后重名的
  （如"默认"与" 默认"），原本就是该名称的一条（没有则 ID 最小的一条）保留，其余加后缀" #<ID>"
  （超长时先截断名称），保证唯一约束不被违反。
  回滚不还原这些数据（上一版代码同样可用）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPLICATION_COLUMNS = [
    ("applicant_username", 50),
    ("applicant_name", 50),
    ("room_name", 110),
]
RECORD_COLUMNS = ["approver_username", "approver_name", "approver_dept_id"]


def _perm_by_scope(column: str) -> str:
    return f"""(
        SELECT jsonb_agg(
            level || jsonb_build_object(
                'approver_perm',
                CASE WHEN level->>'scope' = 'school' THEN 'room:approve_school' ELSE 'room:approve' END
            )
            ORDER BY position
        )
        FROM jsonb_array_elements({column}) WITH ORDINALITY AS t(level, position)
    )"""


def upgrade() -> None:
    for name, length in APPLICATION_COLUMNS:
        op.add_column(
            "applications",
            sa.Column(name, sa.String(length=length), server_default="", nullable=False),
            schema="m2",
        )
    op.add_column(
        "applications",
        sa.Column("occupy_requested_at", sa.DateTime(timezone=True), nullable=True),
        schema="m2",
    )
    op.add_column("approval_records", sa.Column("approver_username", sa.String(length=50)), schema="m2")
    op.add_column("approval_records", sa.Column("approver_name", sa.String(length=50)), schema="m2")
    op.add_column("approval_records", sa.Column("approver_dept_id", sa.Integer()), schema="m2")

    op.execute("UPDATE m2.applications SET applicant_name = '用户' || applicant_id WHERE applicant_name = ''")
    op.execute("UPDATE m2.applications SET room_name = '教室 #' || room_id WHERE room_name = ''")
    op.execute(
        "UPDATE m2.approval_records SET approver_username = '', approver_name = '用户' || approver_id "
        "WHERE approver_id IS NOT NULL AND approver_name IS NULL"
    )
    op.execute(f"UPDATE m2.approval_flows SET levels = {_perm_by_scope('levels')}")
    op.execute(f"UPDATE m2.applications SET flow_snapshot = {_perm_by_scope('flow_snapshot')}")
    # 先排已规范的那一条：它的名称不变，其他行改成的名称都与之不同，逐行检查的唯一约束不会中途冲突
    op.execute("""
        WITH normalized AS (
            SELECT id, name, CASE WHEN btrim(name) = '' THEN '审批流 ' || id ELSE btrim(name) END AS base
            FROM m2.approval_flows
        ), ranked AS (
            SELECT id, name, base,
                   row_number() OVER (PARTITION BY base ORDER BY name <> base, id) AS position
            FROM normalized
        )
        UPDATE m2.approval_flows AS flow
        SET name = CASE
            WHEN ranked.position = 1 THEN ranked.base
            ELSE left(ranked.base, 50 - length(' #' || ranked.id)) || ' #' || ranked.id
        END
        FROM ranked
        WHERE flow.id = ranked.id AND flow.name <> ranked.base
    """)


def downgrade() -> None:
    for name in RECORD_COLUMNS:
        op.drop_column("approval_records", name, schema="m2")
    op.drop_column("applications", "occupy_requested_at", schema="m2")
    for name, _ in APPLICATION_COLUMNS:
        op.drop_column("applications", name, schema="m2")
