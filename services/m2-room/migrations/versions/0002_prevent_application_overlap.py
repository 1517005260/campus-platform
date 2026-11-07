"""prevent overlapping active room applications

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE m2.applications
        ADD CONSTRAINT no_application_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        ) WHERE (status IN ('pending', 'approved'))
        """
    )


def downgrade() -> None:
    op.drop_constraint("no_application_overlap", "applications", schema="m2")
