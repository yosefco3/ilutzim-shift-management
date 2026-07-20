"""
ActivationProfile model — part B (schedule builder).

An activation profile is a **reusable template** that holds positions — a "mode"
of operation (routine / holiday / event). It is NOT a per-week instance: one
"שגרה" template is reused across many weeks. The core workflow is *duplicate +
edit*: copy "שגרה", change one day, save as a new profile (e.g. a mid-week
holiday). Profile↔week binding arrives with the board (task 04).
"""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.schedule_builder.models.position import Position

# Postgres stores these as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ActivationProfile(BaseModel):
    """Reusable schedule template that owns positions."""

    # Display name, free text (e.g. "שגרה", "חג סוכות").
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Free-text category label (e.g. "שגרה" / "חג" / "אירוע" / anything).
    # Deliberately NOT an enum — maximum flexibility (locked with the user).
    kind: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Optional free-text description.
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Per-day free-text labels: day index ("0".."6") -> short label. Day index
    # 0=ראשון … 6=שבת. Shown in the matrix-editor / board headers to annotate a
    # day for the whole profile (e.g. {"4": "ט׳ באב", "5": "ערב שבת"}). An empty
    # map = no special labels (the common case). Keys/values are validated on the
    # ProfileUpdate schema (keys "0".."6", values ≤ 50 chars, blanks dropped).
    day_labels: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}",
    )

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
