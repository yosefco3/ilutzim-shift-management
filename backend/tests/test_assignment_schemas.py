"""Segment validation shared by AssignmentCreate + AssignmentSegmentUpdate (B-5).

The create path previously had NO segment validation, so a malformed or
degenerate segment slipped into the DB and later crashed export/pool at 500.
Both schemas now share ``_SegmentValidatorsMixin``.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schedule_builder.schemas.assignment_schemas import (
    AssignmentCreate,
    AssignmentSegmentUpdate,
)


def _create(**seg):
    return AssignmentCreate(
        position_id=uuid.uuid4(), day_index=0, user_id=uuid.uuid4(), **seg
    )


class TestAssignmentCreateSegment:
    def test_rejects_bad_segment(self):
        with pytest.raises(ValidationError):
            _create(segment_start="7pm", segment_end="15:00")

    def test_rejects_half_segment(self):
        with pytest.raises(ValidationError):
            _create(segment_start="07:00")  # missing segment_end

    def test_rejects_equal_segment(self):
        # s == e is a degenerate window the backend would read as a full 24h day.
        with pytest.raises(ValidationError):
            _create(segment_start="08:00", segment_end="08:00")

    def test_accepts_null_null(self):
        a = _create()
        assert a.segment_start is None and a.segment_end is None

    def test_accepts_valid_pair(self):
        a = _create(segment_start="07:00", segment_end="15:00")
        assert (a.segment_start, a.segment_end) == ("07:00", "15:00")


class TestAssignmentSegmentUpdate:
    def test_rejects_equal_segment(self):
        with pytest.raises(ValidationError):
            AssignmentSegmentUpdate(segment_start="08:00", segment_end="08:00")

    def test_accepts_valid_pair_and_null(self):
        assert AssignmentSegmentUpdate().segment_start is None
        u = AssignmentSegmentUpdate(segment_start="19:00", segment_end="01:00")
        assert (u.segment_start, u.segment_end) == ("19:00", "01:00")

    def test_rejects_bad_format(self):
        with pytest.raises(ValidationError):
            AssignmentSegmentUpdate(segment_start="7:00", segment_end="15:00")
