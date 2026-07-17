"""
Models package — import all models so Alembic autogenerate detects them.
"""

from app.models.base import Base, BaseModel
from app.models.user import User
from app.models.schedule_week import ScheduleWeek
from app.models.weekly_submission import WeeklySubmission
from app.models.daily_status import DailyStatus
from app.models.shift_window import ShiftWindow
from app.models.admin import Admin
from app.models.system_setting import SystemSetting

# Part B (schedule builder) models — imported here ONLY so Alembic autogenerate
# sees them in Base.metadata. The code itself lives under app/schedule_builder/.
from app.schedule_builder.models.activation_profile import ActivationProfile  # noqa: E402,F401
from app.schedule_builder.models.position import Position  # noqa: E402,F401
from app.schedule_builder.models.requirement_attribute import RequirementAttribute  # noqa: E402,F401
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment  # noqa: E402,F401
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment  # noqa: E402,F401
from app.schedule_builder.models.saved_schedule import SavedSchedule  # noqa: E402,F401
from app.schedule_builder.models.actual_schedule import ActualSchedule  # noqa: E402,F401
from app.schedule_builder.models.actual_position import ActualPosition  # noqa: E402,F401
from app.schedule_builder.models.actual_assignment import ActualAssignment  # noqa: E402,F401
from app.schedule_builder.models.actual_reinforcement import ActualReinforcement  # noqa: E402,F401

# Stage 3 (attendance) models — imported here ONLY so Alembic autogenerate
# sees them in Base.metadata. The code itself lives under app/attendance/.
from app.attendance.models.attendance_event import AttendanceEvent  # noqa: E402,F401
from app.attendance.models.attendance_shift import AttendanceShift  # noqa: E402,F401
from app.attendance.models.attendance_adjustment import AttendanceAdjustment  # noqa: E402,F401
from app.attendance.models.attendance_alert_sent import AttendanceAlertSent  # noqa: E402,F401

# Procedure-quiz (סד"פ) models — imported here ONLY so Alembic autogenerate
# sees them in Base.metadata (and so Base.metadata.create_all in tests builds
# them). The code itself lives under app/procedures/.
from app.procedures.models.procedure import Procedure  # noqa: E402,F401
from app.procedures.models.quiz_question import QuizQuestion  # noqa: E402,F401
from app.procedures.models.quiz_attempt import QuizAttempt  # noqa: E402,F401
from app.procedures.models.quiz_poll_link import QuizPollLink  # noqa: E402,F401
from app.procedures.models.procedure_reminder_sent import ProcedureReminderSent  # noqa: E402,F401

__all__ = [
    "Base",
    "BaseModel",
    "User",
    "ScheduleWeek",
    "WeeklySubmission",
    "DailyStatus",
    "ShiftWindow",
    "Admin",
    "SystemSetting",
]
