"""
Stage 3 — Attendance (נוכחות).

This package is the **code boundary** for the attendance system: guards punch
IN/OUT (Telegram first; a physical ZKTeco clock may be added later as just
another event source), the raw punches are stored append-only, paired into
actual shifts, compared against the built schedule, and exported to the payroll
bureau (י.ל.מ) reports.

Dependency rule (one-directional, same as ``app.schedule_builder``):
  • Attendance MAY import from part A (``get_pool``, ``require_admin_role``,
    ``User``, date utils) and MAY *read* from part B (the saved schedule /
    export read-models) — attendance consumes the schedule.
  • Part A / part B MUST NOT import from ``app.attendance`` — the only
    exception is the explicitly-commented model import in
    ``app/models/__init__.py`` so Alembic autogenerate sees the tables.

Week locking and attendance (THE PRINCIPLE, decision 4/7)
---------------------------------------------------------
Week locking (``LOCKED``) applies to *planning*: constraint submission and
board editing. Attendance is a record of *facts after the fact* — punches,
comparisons, admin corrections — and is therefore NEVER gated by week status.
The admin can fix a month-old check-out on a hermetically locked week; guards
punch normally on the live week even though it is LOCKED from the moment it
starts. Pinned by ``tests/test_attendance_locked_weeks.py`` in both directions.

Everything is gated behind the ``ATTENDANCE_ENABLED`` feature flag (off by
default) so the code can ship to production dormant.
"""
