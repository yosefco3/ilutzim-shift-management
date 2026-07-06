"""unique week date range + single-open-week partial index (B-4)

Two structural guards for the week lifecycle:
  - ``uq_schedule_weeks_date_range`` — no two weeks share a (start_date, end_date).
    Blocks the duplicate-week race where concurrent ``auto_rotate_weeks`` calls both
    insert the same upcoming week, after which ``get_by_date_range`` breaks forever
    with MultipleResultsFound.
  - ``uq_one_open_week`` — a partial unique index guaranteeing at most one OPEN week
    at any time (the single-open invariant). The status enum column stores the
    member NAME (uppercase 'OPEN'), so the predicate is ``status = 'OPEN'``.

Revision ID: d3f7a1b9c2e4
Revises: c9e2d4a6f8b1
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3f7a1b9c2e4'
down_revision: Union[str, Sequence[str], None] = 'c9e2d4a6f8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_schedule_weeks_date_range",
        "schedule_weeks",
        ["start_date", "end_date"],
    )
    # At most one OPEN week — the structural net behind the single-open invariant
    # (B-1). Enum is stored by member name, so the label is uppercase 'OPEN'.
    op.create_index(
        "uq_one_open_week",
        "schedule_weeks",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_one_open_week", table_name="schedule_weeks")
    op.drop_constraint(
        "uq_schedule_weeks_date_range", "schedule_weeks", type_="unique"
    )
