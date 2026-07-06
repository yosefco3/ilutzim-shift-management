"""add schedule_assignments (manual assignment, task 05)

One assignment fills a board cell: a guard on a position×day for a week, with an
optional time segment. A cell may hold several assignments (tiling between
guards); a UNIQUE on (week, position, day, user) forbids the same guard twice.

Revision ID: a2c4e6080b13
Revises: d5e7f9b1c3a2
Create Date: 2026-06-29
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2c4e6080b13"
down_revision: Union[str, Sequence[str], None] = "d5e7f9b1c3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("segment_start", sa.String(length=5), nullable=True),
        sa.Column("segment_end", sa.String(length=5), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["week_id"], ["schedule_weeks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "week_id", "position_id", "day_index", "user_id",
            name="uq_assignment_cell_user",
        ),
    )
    op.create_index(
        "ix_schedule_assignments_week_id", "schedule_assignments", ["week_id"]
    )
    op.create_index(
        "ix_schedule_assignments_position_id", "schedule_assignments", ["position_id"]
    )
    op.create_index(
        "ix_schedule_assignments_user_id", "schedule_assignments", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_assignments_user_id", table_name="schedule_assignments")
    op.drop_index("ix_schedule_assignments_position_id", table_name="schedule_assignments")
    op.drop_index("ix_schedule_assignments_week_id", table_name="schedule_assignments")
    op.drop_table("schedule_assignments")
