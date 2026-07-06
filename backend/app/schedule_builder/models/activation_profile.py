"""
ActivationProfile model — part B (schedule builder).

An activation profile is a **reusable template** that holds positions — a "mode"
of operation (routine / holiday / event). It is NOT a per-week instance: one
"שגרה" template is reused across many weeks. The core workflow is *duplicate +
edit*: copy "שגרה", change one day, save as a new profile (e.g. a mid-week
holiday). Profile↔week binding arrives with the board (task 04).
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.schedule_builder.models.position import Position


class ActivationProfile(BaseModel):
    """Reusable schedule template that owns positions."""

    # Display name, free text (e.g. "שגרה", "חג סוכות").
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Free-text category label (e.g. "שגרה" / "חג" / "אירוע" / anything).
    # Deliberately NOT an enum — maximum flexibility (locked with the user).
    kind: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Optional free-text description.
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Marks the seeded "שגרה" profile. Exactly one profile should be True.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )

    # Display order in the management screen.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    # Positions owned by this profile. Deleting a profile deletes its positions
    # (cascade). ``Position.profile_id`` is updatable — moving a position between
    # profiles = reassigning that FK. Duplicating a profile deep-copies these
    # (ProfileService._copy_positions).
    positions: Mapped[list["Position"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Position.display_order",
    )
