"""timeline action admin_accept

管理员代验收此前与报修人验收同记为 accept，现记为 admin_accept：已有记录中验收人不是报修人的改为 admin_accept。
只改数据；回滚到上一版镜像仍能运行（旧代码按字符串读取 action）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE m3.work_order_events e SET action = 'admin_accept'
        FROM m3.work_orders o
        WHERE e.order_id = o.id AND e.action = 'accept' AND e.actor_id <> o.reporter_id
        """
    )


def downgrade() -> None:
    op.execute("UPDATE m3.work_order_events SET action = 'accept' WHERE action = 'admin_accept'")
