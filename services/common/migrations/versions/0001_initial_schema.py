"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-15 18:59:10.003897
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_type", sa.String(length=10), nullable=False),
        sa.Column("actor_id", sa.String(length=50), nullable=False),
        sa.Column("module", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=50), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        schema="common",
    )
    op.create_index("ix_audit_logs_at", "audit_logs", ["at"], unique=False, schema="common")
    op.create_index(
        "ix_audit_logs_target",
        "audit_logs",
        ["module", "target_type", "target_id"],
        unique=False,
        schema="common",
    )
    op.create_table(
        "depts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_depts")),
        sa.UniqueConstraint("name", name=op.f("uq_depts_name")),
        schema="common",
    )
    op.create_table(
        "inbox",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_inbox")),
        schema="common",
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        schema="common",
    )
    op.create_index(
        "ix_notifications_user_read", "notifications", ["user_id", "read_at"], unique=False, schema="common"
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("module", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_permissions")),
        schema="common",
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_roles")),
        schema="common",
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.Column("perm_code", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["perm_code"],
            ["common.permissions.code"],
            name=op.f("fk_role_permissions_perm_code_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["common.roles.code"],
            name=op.f("fk_role_permissions_role_code_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_code", "perm_code", name=op.f("pk_role_permissions")),
        schema="common",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("dept_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dept_id"], ["common.depts.id"], name=op.f("fk_users_dept_id_depts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        schema="common",
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["common.roles.code"],
            name=op.f("fk_user_roles_role_code_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["common.users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_code", name=op.f("pk_user_roles")),
        schema="common",
    )


def downgrade() -> None:
    op.drop_table("user_roles", schema="common")
    op.drop_table("users", schema="common")
    op.drop_table("role_permissions", schema="common")
    op.drop_table("roles", schema="common")
    op.drop_table("permissions", schema="common")
    op.drop_index("ix_notifications_user_read", table_name="notifications", schema="common")
    op.drop_table("notifications", schema="common")
    op.drop_table("inbox", schema="common")
    op.drop_table("depts", schema="common")
    op.drop_index("ix_audit_logs_target", table_name="audit_logs", schema="common")
    op.drop_index("ix_audit_logs_at", table_name="audit_logs", schema="common")
    op.drop_table("audit_logs", schema="common")
