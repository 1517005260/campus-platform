"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12 10:50:18.052836
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
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        schema="m3",
    )
    op.create_index(op.f("ix_m3_outbox_published_at"), "outbox", ["published_at"], unique=False, schema="m3")
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
        schema="m3",
    )
    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("photos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("blocks_room", sa.Boolean(), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("rating_comment", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_orders")),
        schema="m3",
    )
    op.create_index(
        op.f("ix_m3_work_orders_assignee_id"), "work_orders", ["assignee_id"], unique=False, schema="m3"
    )
    op.create_index(
        op.f("ix_m3_work_orders_reporter_id"), "work_orders", ["reporter_id"], unique=False, schema="m3"
    )
    op.create_index(op.f("ix_m3_work_orders_room_id"), "work_orders", ["room_id"], unique=False, schema="m3")
    op.create_index(
        "ix_work_orders_status_deadline", "work_orders", ["status", "deadline_at"], unique=False, schema="m3"
    )
    op.create_table(
        "work_order_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["order_id"], ["m3.work_orders.id"], name=op.f("fk_work_order_events_order_id_work_orders")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_events")),
        schema="m3",
    )
    op.create_index(
        op.f("ix_m3_work_order_events_order_id"), "work_order_events", ["order_id"], unique=False, schema="m3"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_m3_work_order_events_order_id"), table_name="work_order_events", schema="m3")
    op.drop_table("work_order_events", schema="m3")
    op.drop_index("ix_work_orders_status_deadline", table_name="work_orders", schema="m3")
    op.drop_index(op.f("ix_m3_work_orders_room_id"), table_name="work_orders", schema="m3")
    op.drop_index(op.f("ix_m3_work_orders_reporter_id"), table_name="work_orders", schema="m3")
    op.drop_index(op.f("ix_m3_work_orders_assignee_id"), table_name="work_orders", schema="m3")
    op.drop_table("work_orders", schema="m3")
    op.drop_table("settings", schema="m3")
    op.drop_index(op.f("ix_m3_outbox_published_at"), table_name="outbox", schema="m3")
    op.drop_table("outbox", schema="m3")
