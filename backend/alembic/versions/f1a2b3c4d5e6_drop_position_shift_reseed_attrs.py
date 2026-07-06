"""drop positions.shift; reseed requirement attributes to guard characterization

A position is now defined purely by its per-day hours (the security day runs
07:00 → 07:00 next morning) — the morning/afternoon/night ``shift`` column is
removed. The requirement-attribute vocabulary is replaced with the guard
characterization set (אחמ"ש / חמוש / לא חמוש / רכב סיור).

Revision ID: f1a2b3c4d5e6
Revises: d4e6f8a0b2c3
Create Date: 2026-06-25
"""
import uuid
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a0b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Lightweight table handle for the data reseed (avoids importing app models).
_attrs = sa.table(
    "requirement_attributes",
    sa.column("id", sa.Uuid),
    sa.column("key", sa.String),
    sa.column("label", sa.String),
    sa.column("display_order", sa.Integer),
)

_NEW_ATTRS = [
    ("ahmash", 'אחמ"ש'),
    ("armed", "חמוש"),
    ("unarmed", "לא חמוש"),
    ("patrol_vehicle", "רכב סיור"),
]
_OLD_ATTRS = [
    ("armed", "חמוש"),
    ("roni", "רוני"),
    ("vehicle", "רכב עירייה"),
    ("walking", "הליכה מרובה"),
]


def _reseed(rows: list[tuple[str, str]]) -> None:
    op.execute(sa.delete(_attrs))
    op.bulk_insert(
        _attrs,
        [
            {"id": uuid.uuid4(), "key": key, "label": label, "display_order": order}
            for order, (key, label) in enumerate(rows)
        ],
    )


def upgrade() -> None:
    # Drop the shift column (the shared ``shift_type`` enum stays — part A uses it).
    op.drop_column("positions", "shift")
    _reseed(_NEW_ATTRS)


def downgrade() -> None:
    op.add_column(
        "positions",
        sa.Column(
            "shift",
            sa.Enum(name="shift_type", create_type=False),
            nullable=True,
        ),
    )
    _reseed(_OLD_ATTRS)
