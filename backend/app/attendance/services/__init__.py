"""Attendance services package."""

from app.attendance.services.attendance_settings import (
    AttendanceConfig,
    get_attendance_config,
)

__all__ = ["AttendanceConfig", "get_attendance_config"]
