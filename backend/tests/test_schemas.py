"""Tests for Pydantic schema validation."""

import pytest
from datetime import date, time

from app.constants import UserRole
from app.schemas.user_schemas import UserCreate, UserUpdate, _validate_israeli_phone
from app.schemas.week_schemas import WeekCreate
from app.schemas.submission_schemas import (
    ShiftWindowInput,
    DayStatusInput,
    SubmissionCreate,
)


# ── Phone validation ──────────────────────────────────────────────


class TestPhoneValidation:
    """Tests for Israeli phone number validation."""

    def test_valid_mobile(self):
        assert _validate_israeli_phone("0521234567") == "972521234567"

    def test_valid_mobile_with_spaces(self):
        assert _validate_israeli_phone("052 123 4567") == "972521234567"

    def test_valid_mobile_with_dashes(self):
        assert _validate_israeli_phone("052-123-4567") == "972521234567"

    def test_valid_international(self):
        assert _validate_israeli_phone("+972521234567") == "972521234567"

    def test_invalid_too_short(self):
        with pytest.raises(ValueError):
            _validate_israeli_phone("052123456")

    def test_invalid_wrong_prefix(self):
        with pytest.raises(ValueError):
            _validate_israeli_phone("0612345678")

    def test_invalid_letters(self):
        with pytest.raises(ValueError):
            _validate_israeli_phone("052abc4567")

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            _validate_israeli_phone("")


class TestUserCreate:
    """Tests for UserCreate schema."""

    def test_valid_user(self):
        user = UserCreate(
            phone_number="0521234567",
            first_name="ישראל",
            last_name="ישראלי",
            roles=["AHMASH", "ARMED"],
        )
        assert user.phone_number == "972521234567"
        assert user.roles == [UserRole.AHMASH, UserRole.ARMED]

    def test_invalid_phone_rejected(self):
        with pytest.raises(ValueError):
            UserCreate(
                phone_number="123",
                first_name="ישראל",
                last_name="ישראלי",
                roles=["AHMASH"],
            )

    def test_preferred_shift_optional_and_validated(self):
        base = dict(
            phone_number="0521234567",
            first_name="ישראל",
            last_name="ישראלי",
        )
        assert UserCreate(**base).preferred_shift is None
        assert UserCreate(**base, preferred_shift="").preferred_shift == ""
        assert UserCreate(**base, preferred_shift="night").preferred_shift == "night"
        with pytest.raises(ValueError):
            UserCreate(**base, preferred_shift="sunset")


class TestUserUpdate:
    """Tests for UserUpdate schema."""

    def test_none_phone_passes(self):
        update = UserUpdate(first_name="New")
        assert update.phone_number is None

    def test_valid_phone_normalized(self):
        update = UserUpdate(phone_number="052 123 4567")
        assert update.phone_number == "972521234567"

    def test_preferred_shift_empty_string_kept_for_clearing(self):
        # "" must survive validation so the service can translate it to NULL.
        update = UserUpdate(preferred_shift="")
        assert update.preferred_shift == ""

    def test_preferred_shift_invalid_rejected(self):
        with pytest.raises(ValueError):
            UserUpdate(preferred_shift="noon")


# ── Date range validation ─────────────────────────────────────────


class TestWeekCreate:
    """Tests for WeekCreate date validation."""

    def test_valid_range(self):
        week = WeekCreate(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
        )
        assert week.start_date < week.end_date

    def test_same_date_rejected(self):
        with pytest.raises(ValueError):
            WeekCreate(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
            )

    def test_reversed_range_rejected(self):
        with pytest.raises(ValueError):
            WeekCreate(
                start_date=date(2024, 1, 7),
                end_date=date(2024, 1, 1),
            )




# ── Submission validation ─────────────────────────────────────────


class TestShiftWindowInput:
    """Tests for shift window time validation."""

    def test_valid_morning(self):
        sw = ShiftWindowInput(
            shift_type="morning",
            start_time=time(6, 0),
            end_time=time(14, 0),
        )
        assert sw.shift_type.value == "morning"

    def test_valid_night_crossing_midnight(self):
        """Night shifts can cross midnight (start > end)."""
        sw = ShiftWindowInput(
            shift_type="night",
            start_time=time(23, 0),
            end_time=time(7, 0),
        )
        assert sw.shift_type.value == "night"

    def test_same_start_end_rejected(self):
        with pytest.raises(ValueError):
            ShiftWindowInput(
                shift_type="morning",
                start_time=time(8, 0),
                end_time=time(8, 0),
            )

    def test_morning_reversed_rejected(self):
        with pytest.raises(ValueError):
            ShiftWindowInput(
                shift_type="morning",
                start_time=time(14, 0),
                end_time=time(6, 0),
            )


class TestDayStatusInput:
    """Tests for day availability + shift validation."""

    def test_available_with_shifts(self):
        day = DayStatusInput(
            date=date(2024, 1, 1),
            is_available=True,
            shifts=[ShiftWindowInput(
                shift_type="morning",
                start_time=time(6, 0),
                end_time=time(14, 0),
            )],
        )
        assert day.is_available

    def test_unavailable_without_shifts(self):
        day = DayStatusInput(
            date=date(2024, 1, 1),
            is_available=False,
            shifts=[],
        )
        assert not day.is_available

    def test_unavailable_with_shifts_rejected(self):
        with pytest.raises(ValueError):
            DayStatusInput(
                date=date(2024, 1, 1),
                is_available=False,
                shifts=[ShiftWindowInput(
                    shift_type="morning",
                    start_time=time(6, 0),
                    end_time=time(14, 0),
                )],
            )

    def test_available_without_shifts_rejected(self):
        with pytest.raises(ValueError):
            DayStatusInput(
                date=date(2024, 1, 1),
                is_available=True,
                shifts=[],
            )


class TestSubmissionCreate:
    """Tests for submission schema."""

    def test_valid_submission(self):
        sub = SubmissionCreate(
            week_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            days=[
                DayStatusInput(
                    date=date(2024, 1, 1),
                    is_available=True,
                    shifts=[ShiftWindowInput(
                        shift_type="morning",
                        start_time=time(6, 0),
                        end_time=time(14, 0),
                    )],
                )
            ],
        )
        assert len(sub.days) == 1

    def test_empty_days_rejected(self):
        with pytest.raises(ValueError):
            SubmissionCreate(
                week_id="00000000-0000-0000-0000-000000000001",
                user_id="00000000-0000-0000-0000-000000000002",
                days=[],
            )
