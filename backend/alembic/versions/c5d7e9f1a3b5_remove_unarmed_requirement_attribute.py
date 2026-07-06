"""remove the 'unarmed' (לא חמוש) requirement attribute

Position requirements are *limiting* factors — a position may demand "only
armed", "only patrol vehicle", "only אחמ"ש". "לא חמוש" (unarmed) is not a
limiting factor, so it is dropped from the requirement-attribute vocabulary.
The existing row is deleted and the soft key is stripped from any position that
still references it. (Guard characterization keeps UNARMED — this only affects
the per-position requirement vocabulary.)

Revision ID: c5d7e9f1a3b5
Revises: a2c4e6080b13
Create Date: 2026-06-29
"""
import uuid
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d7e9f1a3b5"
down_revision: Union[str, Sequence[str], None] = "a2c4e6080b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_attrs = sa.table(
    "requirement_attributes",
    sa.column("id", sa.Uuid),
    sa.column("key", sa.String),
    sa.column("label", sa.String),
    sa.column("display_order", sa.Integer),
)
_positions = sa.table(
    "positions",
    sa.column("id", sa.Uuid),
    sa.column("required_attributes", sa.JSON),
)


def _strip_key_from_positions(key: str) -> None:
    """Remove ``key`` from every position's required_attributes list."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_positions.c.id, _positions.c.required_attributes)
    ).fetchall()
    for pos_id, required in rows:
        if not required or key not in required:
            continue
        bind.execute(
            sa.update(_positions)
            .where(_positions.c.id == pos_id)
            .values(required_attributes=[k for k in required if k != key])
        )


def upgrade() -> None:
    _strip_key_from_positions("unarmed")
    op.execute(sa.delete(_attrs).where(_attrs.c.key == "unarmed"))


def downgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.select(_attrs.c.id).where(_attrs.c.key == "unarmed")
    ).first()
    if exists is None:
        max_order = bind.execute(
            sa.select(sa.func.max(_attrs.c.display_order))
        ).scalar()
        op.bulk_insert(
            _attrs,
            [
                {
                    "id": uuid.uuid4(),
                    "key": "unarmed",
                    "label": "לא חמוש",
                    "display_order": (max_order or 0) + 1,
                }
            ],
        )
