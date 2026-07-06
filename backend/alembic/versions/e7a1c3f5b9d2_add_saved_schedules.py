"""add saved_schedules (frozen schedule snapshot per week)

A saved schedule is a self-contained snapshot of a week's built board +
assignments. It deliberately has NO foreign key to profile/position — position
names and guard names are copied inline into the ``snapshot`` JSON — so deleting
the activation profile (which cascades positions → assignments) leaves the saved
schedule intact. The only FK is ``week_id`` (CASCADE): the snapshot is removed
only if the week itself is deleted. ``week_id`` is UNIQUE (one snapshot per week).

Revision ID: e7a1c3f5b9d2
Revises: c5d7e9f1a3b5
Create Date: 2026-07-01
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e7a1c3f5b9d2"
down_revision: Union[str, Sequence[str], None] = "c5d7e9f1a3b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=True),
        sa.Column(
            "snapshot",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["week_id"], ["schedule_weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # UNIQUE index on week_id — one snapshot per week (re-saving upserts).
    op.create_index(
        "ix_saved_schedules_week_id", "saved_schedules", ["week_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_saved_schedules_week_id", table_name="saved_schedules")
    op.drop_table("saved_schedules")
