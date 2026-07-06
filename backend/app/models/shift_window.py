"""
ShiftWindow model — time window for a specific shift type.
"""

import uuid
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ShiftType
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.daily_status import DailyStatus


class ShiftWindow(BaseModel):
    """Shift time window within a daily status."""

    daily_status_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_statuses.id", ondelete="CASCADE"), nullable=False,
    )
    shift_type: Mapped[ShiftType] = mapped_column(
        Enum(ShiftType, name="shift_type"), nullable=False,
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Relationships
    daily_status: Mapped["DailyStatus"] = relationship(back_populates="shift_windows")
