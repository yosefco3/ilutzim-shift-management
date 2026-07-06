"""
Enums and default values for the application.
"""

import enum


class ShiftType(str, enum.Enum):
    """Shift types throughout the day."""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"


class WeekStatus(str, enum.Enum):
    """Weekly schedule lifecycle status (3-state model, no reopening).

    Lifecycle: CLOSED (upcoming, never opened) → OPEN → CLOSED (board-building,
    publishable) → LOCKED (final, rollover-only). A week is never reopened.

    CLOSED  — submission window closed. If ``opened_at`` is set the window already
              ran and the week will NOT open again — this is the board-building
              state. "Publish" broadcasts the schedule and stamps ``published_at``
              but keeps the week CLOSED (it never locks), so the admin can keep
              editing the board and re-publish until the week starts. If
              ``opened_at`` is NULL it is the upcoming week waiting to be opened.
    OPEN    — submissions accepted. Allowed ONLY for the upcoming, never-opened week
              and only when no other week is OPEN (at most one OPEN week).
    LOCKED  — final, non-reopenable. Reached ONLY by the Sunday rollover when the
              week's ``start_date`` arrives; it locks BOTH the board and constraint
              submission. No publish/manual path produces LOCKED. There is no
              PUBLISHED state — ``published_at`` tracks publishing instead.
    """
    CLOSED = "closed"
    OPEN = "open"
    LOCKED = "locked"


class SubmissionStatus(str, enum.Enum):
    """Status of a guard's weekly submission."""
    SUBMITTED = "submitted"
    SUBMITTED_WITH_VARIANCE = "submitted_with_variance"
    PENDING = "pending"
    AUTO_ABSENCE = "auto_absence"


class UserRole(str, enum.Enum):
    """Guard attributes — a guard may hold several at once (multi-select)."""
    ARMED = "ARMED"
    UNARMED = "UNARMED"
    AHMASH = "AHMASH"
    PATROL_VEHICLE = "PATROL_VEHICLE"


class AdminRole(str, enum.Enum):
    """Admin roles with hierarchical permissions.

    - super_admin: full access to everything
    - admin: manage guards, weeks
    - viewer: read-only access
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    VIEWER = "viewer"