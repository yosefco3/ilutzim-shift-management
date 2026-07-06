"""
Saved-schedule schemas (part B — frozen schedule snapshot).

Metadata payloads only — the large snapshot JSON is not returned by the JSON
endpoints; it is consumed server-side by the Excel download.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SavedScheduleResponse(BaseModel):
    """Metadata for a week's saved snapshot (which weeks have one + when saved)."""
    week_id: uuid.UUID
    profile_name: str | None = None
    saved_at: datetime

    @classmethod
    def from_orm(cls, s) -> "SavedScheduleResponse":
        """Build from a SavedSchedule row (``updated_at`` is the last-saved time)."""
        return cls(
            week_id=s.week_id,
            profile_name=s.profile_name,
            saved_at=s.updated_at,
        )
