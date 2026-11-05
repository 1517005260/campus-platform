"""notification email attempts：邮件逐条失败计数与最近错误（只新增列，旧版本镜像仍可运行）

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 13:01:33.232977
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("email_attempts", sa.Integer(), server_default="0", nullable=False),
        schema="common",
    )
    op.add_column(
        "notifications", sa.Column("email_last_error", sa.String(length=200), nullable=True), schema="common"
    )


def downgrade() -> None:
    op.drop_column("notifications", "email_last_error", schema="common")
    op.drop_column("notifications", "email_attempts", schema="common")
