"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12 10:49:03.879170
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
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("applicant_dept_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("attendees", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("flow_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_level", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("m1_block_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_applications_time_order")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        schema="m2",
    )
    op.create_index(
        "ix_applications_room_time", "applications", ["room_id", "start_at"], unique=False, schema="m2"
    )
    op.create_index(
        "ix_applications_status_deadline",
        "applications",
        ["status", "deadline_at"],
        unique=False,
        schema="m2",
    )
    op.create_index(
        op.f("ix_m2_applications_applicant_id"), "applications", ["applicant_id"], unique=False, schema="m2"
    )
    op.create_table(
        "approval_flows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("room_type", sa.String(length=20), nullable=True),
        sa.Column("dept_scoped", sa.Boolean(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("levels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_flows")),
        sa.UniqueConstraint("name", name=op.f("uq_approval_flows_name")),
        schema="m2",
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        schema="m2",
    )
    op.create_index(op.f("ix_m2_outbox_published_at"), "outbox", ["published_at"], unique=False, schema="m2")
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
        schema="m2",
    )
    op.create_table(
        "approval_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["m2.applications.id"],
            name=op.f("fk_approval_records_application_id_applications"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_records")),
        schema="m2",
    )
    op.create_index(
        op.f("ix_m2_approval_records_application_id"),
        "approval_records",
        ["application_id"],
        unique=False,
        schema="m2",
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_m2_approval_records_application_id"), table_name="approval_records", schema="m2")
    op.drop_table("approval_records", schema="m2")
    op.drop_table("settings", schema="m2")
    op.drop_index(op.f("ix_m2_outbox_published_at"), table_name="outbox", schema="m2")
    op.drop_table("outbox", schema="m2")
    op.drop_table("approval_flows", schema="m2")
    op.drop_index(op.f("ix_m2_applications_applicant_id"), table_name="applications", schema="m2")
    op.drop_index("ix_applications_status_deadline", table_name="applications", schema="m2")
    op.drop_index("ix_applications_room_time", table_name="applications", schema="m2")
    op.drop_table("applications", schema="m2")
