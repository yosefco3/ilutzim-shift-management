"""Schedule week schemas with date range validation."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.constants import WeekStatus
from app.messages import Messages


class WeekCreate(BaseModel):
    """Schema for creating a schedule week."""
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "WeekCreate":
        if self.end_date <= self.start_date:
            raise ValueError(Messages.VAL_DATE_RANGE)
        return self


class WeekStatusUpdate(BaseModel):
    """Schema for updating week status."""
    status: WeekStatus


class WeekResponse(BaseModel):
    """Schema for week data in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    start_date: date
    end_date: date
    status: WeekStatus
    # When the week was first opened (NULL = never opened). The admin UI uses this
    # to show "open" only for the upcoming, never-opened week (no reopening).
    opened_at: datetime | None = None
    # When the schedule was last broadcast via "publish" (NULL = never published).
    # Publish keeps the week CLOSED, so this — not the status — is what tells the
    # UI to show "publish" vs "re-publish".
    published_at: datetime | None = None
    # Number of guards who submitted for this week. Populated by the weeks
    # endpoint (defaults to 0 so single-week responses stay valid).
    submission_count: int = 0

    @computed_field
    @property
    def week_label(self) -> str:
        """Human-readable week label, e.g. 'שבוע 01/06 - 07/06'."""
        return f"שבוע {self.start_date.strftime('%d/%m')} – {self.end_date.strftime('%d/%m')}"


class PublishResult(BaseModel):
    """Summary returned by the publish action — how many guards were notified,
    and whether this was a re-publish (the week already had ``published_at``) vs
    a first publish. The week's status is unchanged by publishing (stays CLOSED)."""
    sent: int = 0
    skipped: int = 0
    failed: int = 0  # had a telegram_id but delivery failed — surfaced for the admin
    total: int = 0
    republished: bool = False


class PublishPreviewItem(BaseModel):
    """One guard's entry in the publish *preview* — the exact Telegram message
    they would receive on publish, plus who they are, so the admin can verify
    content and recipients without sending. Nothing is delivered."""
    user_name: str
    phone_number: str = ""
    telegram_id: str | None = None
    # False when the guard has no telegram_id — the real broadcast skips them.
    would_send: bool = False
    message: str


class DayItem(BaseModel):
    """Single day in a week's submission form."""
    day_index: int
    blocked: bool = False


class WeekWithDaysResponse(WeekResponse):
    """Week data with 7 days for the submission form."""
    days: list[DayItem]
