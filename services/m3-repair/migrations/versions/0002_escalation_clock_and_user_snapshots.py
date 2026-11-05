"""escalation clock, block start time and user snapshots

先扩展：新增列都可空或带默认值，回滚到上一版镜像仍能运行（旧代码不写这些列，status_changed_at 取默认值）。
已有工单的计时起点从时间线回填，升级任务上线后不会把老工单当成刚进入当前状态。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 20:37:22.820804
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("dept_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_snapshots")),
        schema="m3",
    )
    op.add_column(
        "work_orders",
        sa.Column(
            "status_changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        schema="m3",
    )
    op.add_column(
        "work_orders", sa.Column("last_escalated_at", sa.DateTime(timezone=True), nullable=True), schema="m3"
    )
    op.add_column(
        "work_orders", sa.Column("block_start_at", sa.DateTime(timezone=True), nullable=True), schema="m3"
    )
    op.execute(
        """
        UPDATE m3.work_orders o SET
          status_changed_at = COALESCE(
            (SELECT max(e.at) FROM m3.work_order_events e
             WHERE e.order_id = o.id AND e.to_status = o.status AND e.action <> 'escalate'),
            o.created_at),
          last_escalated_at = (SELECT max(e.at) FROM m3.work_order_events e
                               WHERE e.order_id = o.id AND e.action = 'escalate')
        """
    )


def downgrade() -> None:
    op.drop_column("work_orders", "block_start_at", schema="m3")
    op.drop_column("work_orders", "last_escalated_at", schema="m3")
    op.drop_column("work_orders", "status_changed_at", schema="m3")
    op.drop_table("user_snapshots", schema="m3")
