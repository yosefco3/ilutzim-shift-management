"""
Position model — part B (schedule builder).

A *position* (עמדה) is one row in the schedule = a requirement for **one** guard.
Two guards at the same physical spot = two positions. A position belongs to an
``ActivationProfile`` and carries:

- ``day_schedules``       — per-day hours AND active-days in one JSON map:
                            ``{"0": {"start": "07:30", "end": "15:00"}, ...}``.
                            A day index present = that day is active; missing =
                            inactive. Day index 0=ראשון … 6=שבת. There is no
                            separate "shift" concept — a position is defined purely
                            by its hours. The security day runs 07:00 → 07:00 the
                            next morning, so ``end <= start`` wraps past midnight
                            (e.g. a night window 23:00→07:00).
- ``required_attributes`` — list of attribute *keys* (e.g. ``["armed", "roni"]``)
                            referencing the configurable RequirementAttribute
                            vocabulary. The link is **soft** (no hard FK), so the
                            vocabulary can change without breaking positions.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.schedule_builder.models.activation_profile import ActivationProfile

# Postgres stores these as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Position(BaseModel):
    """One schedule row = a requirement for a single guard."""

    # Owning profile. nullable=False but **updatable** — moving a position
    # between profiles = reassigning this FK. CASCADE: deleting a profile
    # deletes its positions.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activation_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Display name (e.g. "ארנונה", "קומה 6", "סייר 1").
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Per-day hours + active days in one map: day index ("0".."6") -> {start,end}.
    # Presence of a key = active that day; missing = inactive.
    day_schedules: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}",
    )

    # Required attribute keys (soft reference to RequirementAttribute vocabulary).
    required_attributes: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default="[]",
    )

    # Display order within the owning profile.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    # Event / non-splitting position (רענון, ישיבת מועצה). When True, several
    # guards attend the SAME window simultaneously — the cell is never tiled/split
    # between them, the ≤2-guard cap is lifted, and the cell has no coverage
    # requirement (an empty event cell is a valid state). Default False = a normal
    # position (one guard per window, tiled when a second joins).
    is_event: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )

    # Event positions only: a FIXED participant count (e.g. ישיבת מועצה needs 4).
    # None = unlimited (רענון — any number attend, no tiling). A positive int
    # tiles the cell into that many participant slots; missing slots render as a
    # highlighted hole and the cell caps at this many guards. Always None when
    # ``is_event`` is False (enforced by the service).
    event_required_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )

    profile: Mapped["ActivationProfile"] = relationship(back_populates="positions")
