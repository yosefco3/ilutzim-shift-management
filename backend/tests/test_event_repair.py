"""Tests for the event-flag repair planner (build_repair_plan).

Pure logic, no DB — mirrors what scripts/repair_event_flags.py plans before it
touches any row.
"""

from types import SimpleNamespace

from app.schedule_builder.utils.event_repair import RepairItem, build_repair_plan


def _pos(profile_name, pid, name, is_event, count):
    return SimpleNamespace(
        profile_name=profile_name,
        id=pid,
        name=name,
        is_event=is_event,
        event_required_count=count,
    )


# The base has an unlimited event ("רענון") and a fixed-count one ("טווסים", 3).
BASE = {"רענון": None, "טווסים יום ו": 3}


def test_damaged_copy_is_planned_with_base_count():
    # A copy where both events were stripped to is_event=False, count=None.
    candidates = [
        _pos("שגרה (עותק)", "p1", "רענון", False, None),
        _pos("שגרה (עותק)", "p2", "טווסים יום ו", False, None),
    ]
    plan = build_repair_plan(BASE, candidates)
    assert plan == [
        RepairItem("שגרה (עותק)", "p1", "רענון", None),
        RepairItem("שגרה (עותק)", "p2", "טווסים יום ו", 3),
    ]


def test_existing_count_is_not_overwritten():
    # Defensive: a candidate that somehow still has a real count keeps it.
    candidates = [_pos("חג", "p3", "טווסים יום ו", False, 5)]
    plan = build_repair_plan(BASE, candidates)
    assert plan == [RepairItem("חג", "p3", "טווסים יום ו", 5)]


def test_already_event_is_skipped():
    candidates = [_pos("חג", "p4", "רענון", True, None)]
    assert build_repair_plan(BASE, candidates) == []


def test_renamed_or_unmatched_is_skipped():
    # A position whose name isn't a base event → not our concern.
    candidates = [_pos("חג", "p5", "רענון ששונה שמו", False, None)]
    assert build_repair_plan(BASE, candidates) == []


def test_normal_position_sharing_no_name_is_skipped():
    candidates = [_pos("חג", "p6", "קומה 6", False, None)]
    assert build_repair_plan(BASE, candidates) == []


def test_empty_base_events_plans_nothing():
    candidates = [_pos("חג", "p7", "רענון", False, None)]
    assert build_repair_plan({}, candidates) == []


def test_mixed_batch_only_damaged_events_planned():
    candidates = [
        _pos("עותק", "a", "רענון", False, None),        # repair
        _pos("עותק", "b", "רענון", True, None),         # already event → skip
        _pos("עותק", "c", "קומה 6", False, None),       # not an event name → skip
        _pos("עותק", "d", "טווסים יום ו", False, None), # repair (count 3)
    ]
    plan = build_repair_plan(BASE, candidates)
    assert [(i.position_id, i.set_count) for i in plan] == [("a", None), ("d", 3)]
