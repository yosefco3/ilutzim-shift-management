"""
RequirementAttribute model — part B (schedule builder).

A *requirement attribute* is one entry in the **configurable** vocabulary of
guard requirements (חמוש / רוני / רכב עירייה / הליכה מרובה / אחמ"ש ...). Positions
reference these by ``key`` (a soft, FK-less link in ``Position.required_attributes``).

The whole point is flexibility: the guard-attribute taxonomy is not finalized, so
adding/renaming an attribute must be a **data** change (a new row, editable from
the UI) — never a migration or deploy.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RequirementAttribute(BaseModel):
    """One configurable guard-requirement attribute (key -> Hebrew label)."""

    # Stable machine key (slug), referenced by Position.required_attributes.
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)

    # Hebrew display label (e.g. "חמוש", "רכב עירייה").
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    # Display order in the management UI.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
