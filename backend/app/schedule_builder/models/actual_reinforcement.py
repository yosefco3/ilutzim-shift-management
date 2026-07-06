"""
ActualReinforcement model — a "מתגבר" card (actual-schedule feature, step 11).

A reinforcement guard is an external, one-off helper brought in for days the
team can't cover. The card ties a flagged ``User`` row (``is_reinforcement``)
to one week's actual schedule — the card is what puts them in that week's
pool. One-off by decision: a returning helper gets a new card (and user row)
on the week that needs them.

Deleting the card (the admin removing the reinforcement) also deletes the
user row via the service — the whole point of one-off. Deleting the week
cascades the card; the flagged user row may linger, invisible everywhere
(filtered by ``is_reinforcement``), which is accepted.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.schedule_builder.models.actual_schedule import ActualSchedule


class ActualReinforcement(BaseModel):
    """One reinforcement card: an external guard in one week's actual pool."""

    # The week's actual schedule this card belongs to. CASCADE: deleting the
    # copy (week purge) drops the card.
    actual_schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actual_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The flagged user row carrying the name/phone. CASCADE both ways: the
    # service deletes the user when the card is removed.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The external supervisor responsible for this helper (optional) — a
    # property of the engagement, so it lives on the card, not the user.
    # Surfaces in the reinforcements report.
    supervisor_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None,
    )

    actual_schedule: Mapped["ActualSchedule"] = relationship()
    user: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "actual_schedule_id", "user_id",
            name="uq_actual_reinforcement_week_user",
        ),
    )
