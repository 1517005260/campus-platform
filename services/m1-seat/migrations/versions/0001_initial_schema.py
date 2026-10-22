"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12 10:46:20.163355
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
    # 排除约束里 seat_id/user_id 的 "=" 需要 btree_gist（生产库由 deploy/postgres 初始化脚本预先创建）
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "idempotency_keys",
        sa.Column("caller", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("caller", "key", name=op.f("pk_idempotency_keys")),
        schema="m1",
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
        schema="m1",
    )
    op.create_index(op.f("ix_m1_outbox_published_at"), "outbox", ["published_at"], unique=False, schema="m1")
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building", sa.String(length=50), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("dept_id", sa.Integer(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_study_room", sa.Boolean(), nullable=False),
        sa.Column("is_whole_bookable", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rooms")),
        sa.UniqueConstraint("building", "name", name=op.f("uq_rooms_building_name")),
        schema="m1",
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
        schema="m1",
    )
    op.create_table(
        "checkin_codes",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("valid_date", sa.Date(), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["m1.rooms.id"], name=op.f("fk_checkin_codes_room_id_rooms")),
        sa.PrimaryKeyConstraint("room_id", "valid_date", name=op.f("pk_checkin_codes")),
        schema="m1",
    )
    op.create_table(
        "room_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["m1.rooms.id"], name=op.f("fk_room_blocks_room_id_rooms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_blocks")),
        sa.UniqueConstraint("source", "ref_id", name=op.f("uq_room_blocks_source_ref_id")),
        schema="m1",
    )
    op.create_index(op.f("ix_m1_room_blocks_room_id"), "room_blocks", ["room_id"], unique=False, schema="m1")
    op.create_table(
        "room_open_hours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_hour", sa.Integer(), nullable=False),
        sa.Column("close_hour", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "open_hour >= 0 AND close_hour <= 24 AND open_hour < close_hour",
            name=op.f("ck_room_open_hours_hours"),
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_room_open_hours_weekday_range")),
        sa.ForeignKeyConstraint(
            ["room_id"], ["m1.rooms.id"], name=op.f("fk_room_open_hours_room_id_rooms"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_open_hours")),
        sa.UniqueConstraint("room_id", "weekday", name=op.f("uq_room_open_hours_room_id_weekday")),
        schema="m1",
    )
    op.create_table(
        "seats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("outlet", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["m1.rooms.id"], name=op.f("fk_seats_room_id_rooms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seats")),
        sa.UniqueConstraint("room_id", "code", name=op.f("uq_seats_room_id_code")),
        schema="m1",
    )
    op.create_index(op.f("ix_m1_seats_room_id"), "seats", ["room_id"], unique=False, schema="m1")
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cancel_reason", sa.String(length=30), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_before_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_late_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        postgresql.ExcludeConstraint(
            (sa.text("seat_id"), "="),
            (sa.text("tstzrange(start_at, end_at)"), "&&"),
            where=sa.text("status IN ('booked', 'checked_in')"),
            using="gist",
            name="no_seat_overlap",
        ),
        postgresql.ExcludeConstraint(
            (sa.text("user_id"), "="),
            (sa.text("tstzrange(start_at, end_at)"), "&&"),
            where=sa.text("status IN ('booked', 'checked_in')"),
            using="gist",
            name="no_user_overlap",
        ),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_reservations_time_order")),
        sa.ForeignKeyConstraint(["room_id"], ["m1.rooms.id"], name=op.f("fk_reservations_room_id_rooms")),
        sa.ForeignKeyConstraint(["seat_id"], ["m1.seats.id"], name=op.f("fk_reservations_seat_id_seats")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservations")),
        schema="m1",
    )
    op.create_index(
        op.f("ix_m1_reservations_user_id"), "reservations", ["user_id"], unique=False, schema="m1"
    )
    op.create_index(
        "ix_reservations_status_start", "reservations", ["status", "start_at"], unique=False, schema="m1"
    )
    op.create_table(
        "seat_status_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["seat_id"], ["m1.seats.id"], name=op.f("fk_seat_status_logs_seat_id_seats")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seat_status_logs")),
        schema="m1",
    )
    op.create_index(
        "ix_seat_status_logs_seat_at", "seat_status_logs", ["seat_id", "at"], unique=False, schema="m1"
    )
    op.create_table(
        "violations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["m1.reservations.id"], name=op.f("fk_violations_reservation_id_reservations")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_violations")),
        sa.UniqueConstraint("reservation_id", name=op.f("uq_violations_reservation_id")),
        schema="m1",
    )
    op.create_index(op.f("ix_m1_violations_user_id"), "violations", ["user_id"], unique=False, schema="m1")


def downgrade() -> None:
    op.drop_index(op.f("ix_m1_violations_user_id"), table_name="violations", schema="m1")
    op.drop_table("violations", schema="m1")
    op.drop_index("ix_seat_status_logs_seat_at", table_name="seat_status_logs", schema="m1")
    op.drop_table("seat_status_logs", schema="m1")
    op.drop_index("ix_reservations_status_start", table_name="reservations", schema="m1")
    op.drop_index(op.f("ix_m1_reservations_user_id"), table_name="reservations", schema="m1")
    op.drop_table("reservations", schema="m1")
    op.drop_index(op.f("ix_m1_seats_room_id"), table_name="seats", schema="m1")
    op.drop_table("seats", schema="m1")
    op.drop_table("room_open_hours", schema="m1")
    op.drop_index(op.f("ix_m1_room_blocks_room_id"), table_name="room_blocks", schema="m1")
    op.drop_table("room_blocks", schema="m1")
    op.drop_table("checkin_codes", schema="m1")
    op.drop_table("settings", schema="m1")
    op.drop_table("rooms", schema="m1")
    op.drop_index(op.f("ix_m1_outbox_published_at"), table_name="outbox", schema="m1")
    op.drop_table("outbox", schema="m1")
    op.drop_table("idempotency_keys", schema="m1")
