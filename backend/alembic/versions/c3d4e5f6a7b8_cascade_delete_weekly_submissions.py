"""add ON DELETE CASCADE to weekly_submissions.week_id

Data retention purges old weeks (keep only the most recent N). For a week
deletion to cleanly remove its submissions in bulk, the
weekly_submissions.week_id FK must cascade at the database level. The further
links (daily_statuses.submission_id, shift_windows.daily_status_id) already
have ON DELETE CASCADE, so the whole chain drops in one statement.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "weekly_submissions_week_id_fkey"


def upgrade() -> None:
    """Recreate the week_id FK with ON DELETE CASCADE."""
    op.drop_constraint(_FK_NAME, "weekly_submissions", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "weekly_submissions",
        "schedule_weeks",
        ["week_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Restore the plain (non-cascading) week_id FK."""
    op.drop_constraint(_FK_NAME, "weekly_submissions", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "weekly_submissions",
        "schedule_weeks",
        ["week_id"],
        ["id"],
    )
