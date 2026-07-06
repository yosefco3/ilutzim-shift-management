"""Canonical soft-warning engine — per-cell rules (ported 1:1 from warnings.js)."""

from app.schedule_builder.services.warnings_service import compute_board_warnings


def _cell(day_index, active=True, window=None, is_override=False):
    return {"day_index": day_index, "active": active,
            "window": window, "is_override": is_override}


def _row(position_id="pos1", name="ארנונה", band="morning",
         window=("07:00", "15:00"), required_attributes=None,
         is_event=False, event_required_count=None, active_days=(0,)):
    win = {"start": window[0], "end": window[1]} if window else None
    return {
        "position_id": position_id,
        "name": name,
        "band": band,
        "required_attributes": required_attributes or [],
        "is_event": is_event,
        "event_required_count": event_required_count,
        "cells": [
            _cell(d, active=d in active_days, window=win if d in active_days else None)
            for d in range(7)
        ],
    }


def _board(rows):
    return {"rows": rows}


def _guard(gid, full_name="נתן", roles=None, availability=None):
    return {"id": gid, "full_name": full_name, "roles": roles or [],
            "availability": availability or {}}


def _assign(user_id, full_name="נתן", roles=None, segment_start=None, segment_end=None):
    return {"user_id": user_id, "user_full_name": full_name,
            "user_roles": roles or [], "segment_start": segment_start,
            "segment_end": segment_end}


# ── out_of_availability / partial_coverage / full (no warning) ───────────────

def test_full_coverage_no_warning():
    board = _board([_row(window=("07:00", "15:00"))])
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "15:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    assert res["by_cell"] == {}
    assert res["summary"]["total"] == 0


def test_out_of_availability_hard():
    board = _board([_row(window=("07:00", "15:00"))])
    pool = [_guard("u1", availability={"0": [{"start": "19:00", "end": "23:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    assert [w["type"] for w in res["by_cell"]["pos1:0"]] == ["out_of_availability"]
    assert res["summary"]["out_of_availability"] == 1


def test_partial_coverage_soft_with_gaps():
    board = _board([_row(window=("07:00", "15:00"))])
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "11:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    w = res["by_cell"]["pos1:0"][0]
    assert w["type"] == "partial_coverage"
    assert w["gaps"] == [{"start": "11:00", "end": "15:00"}]


# ── cross-midnight coverage on the anchor axis (the B-2 axis) ────────────────

def test_cross_midnight_full_coverage_no_warning():
    board = _board([_row(band="night", window=("23:00", "07:00"))])
    pool = [_guard("u1", availability={"0": [{"start": "23:00", "end": "07:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    assert res["by_cell"] == {}


def test_cross_midnight_partial_coverage():
    board = _board([_row(band="night", window=("23:00", "07:00"))])
    # Available only the first half of the night → partial, gap 03:00–07:00.
    pool = [_guard("u1", availability={"0": [{"start": "23:00", "end": "03:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    w = res["by_cell"]["pos1:0"][0]
    assert w["type"] == "partial_coverage"
    assert w["gaps"] == [{"start": "03:00", "end": "07:00"}]


# ── missing_attribute (case-insensitive) ─────────────────────────────────────

def test_missing_attribute_hard():
    board = _board([_row(required_attributes=["armed"])])
    pool = [_guard("u1", roles=[], availability={"0": [{"start": "07:00", "end": "15:00"}]})]
    ac = {"pos1:0": [_assign("u1", roles=[])]}
    res = compute_board_warnings(board, ac, pool)
    w = next(w for w in res["by_cell"]["pos1:0"] if w["type"] == "missing_attribute")
    assert w["missing"] == ["armed"]


def test_attribute_held_case_insensitive_no_warning():
    board = _board([_row(required_attributes=["armed"])])
    pool = [_guard("u1", roles=["ARMED"], availability={"0": [{"start": "07:00", "end": "15:00"}]})]
    ac = {"pos1:0": [_assign("u1", roles=["ARMED"])]}
    res = compute_board_warnings(board, ac, pool)
    assert res["by_cell"] == {}


# ── double_booking (overlap, same day) ───────────────────────────────────────

def test_double_booking_hard():
    rows = [
        _row(position_id="pos1", name="ארנונה", band="morning", window=("07:00", "15:00")),
        _row(position_id="pos2", name="קומה 6", band="morning", window=("11:00", "19:00")),
    ]
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "19:00"}]})]
    ac = {"pos1:0": [_assign("u1")], "pos2:0": [_assign("u1")]}
    res = compute_board_warnings(_board(rows), ac, pool)
    p1 = next(w for w in res["by_cell"]["pos1:0"] if w["type"] == "double_booking")
    p2 = next(w for w in res["by_cell"]["pos2:0"] if w["type"] == "double_booking")
    assert p1["other_position"] == "קומה 6"
    assert p2["other_position"] == "ארנונה"


# ── already_in_shift (same band, same day, no overlap needed) ────────────────

def test_already_in_shift_soft():
    rows = [
        _row(position_id="pos1", name="A", band="morning", window=("07:00", "11:00")),
        _row(position_id="pos2", name="B", band="morning", window=("11:00", "15:00")),
    ]
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "15:00"}]})]
    ac = {"pos1:0": [_assign("u1")], "pos2:0": [_assign("u1")]}
    res = compute_board_warnings(_board(rows), ac, pool)
    assert any(w["type"] == "already_in_shift" for w in res["by_cell"]["pos1:0"])
    assert any(w["type"] == "already_in_shift" for w in res["by_cell"]["pos2:0"])
    # Adjacent (non-overlapping) windows → NOT a double_booking.
    assert not any(w["type"] == "double_booking" for w in res["by_cell"]["pos1:0"])


# ── understaffed_event ───────────────────────────────────────────────────────

def test_understaffed_event_soft():
    board = _board([_row(is_event=True, event_required_count=4, band="morning")])
    pool = [_guard("u1"), _guard("u2", full_name="דנה")]
    ac = {"pos1:0": [_assign("u1"), _assign("u2", full_name="דנה")]}
    res = compute_board_warnings(board, ac, pool)
    w = res["by_cell"]["pos1:0"][0]
    assert w == {"type": "understaffed_event", "need": 4, "have": 2}


def test_event_fully_staffed_no_warning():
    board = _board([_row(is_event=True, event_required_count=2, band="morning")])
    pool = [_guard("u1"), _guard("u2", full_name="דנה")]
    ac = {"pos1:0": [_assign("u1"), _assign("u2", full_name="דנה")]}
    res = compute_board_warnings(board, ac, pool)
    assert res["by_cell"] == {}


def test_zero_guard_event_day_not_understaffed():
    board = _board([_row(is_event=True, event_required_count=4, band="morning")])
    res = compute_board_warnings(board, {}, [])
    assert res["by_cell"] == {}


# ── per-guard timeline rules (step 02) ───────────────────────────────────────

def _multiday_row(position_id="pos1", name="ארנונה", band="morning",
                  window=("07:00", "15:00"), active_days=range(7)):
    win = {"start": window[0], "end": window[1]}
    return {
        "position_id": position_id, "name": name, "band": band,
        "required_attributes": [], "is_event": False, "event_required_count": None,
        "cells": [
            _cell(d, active=d in active_days, window=win if d in active_days else None)
            for d in range(7)
        ],
    }


def test_over_continuous_hours_hard():
    # One 13h block (07:00–20:00) > 12h cap → warning.
    board = _board([_multiday_row(window=("07:00", "20:00"), active_days=[0])])
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "20:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    w = next(w for w in res["by_guard"]["u1"] if w["type"] == "over_continuous_hours")
    assert w["hours"] == 13


def test_eleven_hour_block_no_over_continuous():
    board = _board([_multiday_row(window=("07:00", "18:00"), active_days=[0])])
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "18:00"}]})]
    ac = {"pos1:0": [_assign("u1")]}
    res = compute_board_warnings(board, ac, pool)
    assert "u1" not in res["by_guard"]


def test_insufficient_rest_hard():
    # Day 0 morning 07:00–11:00, then day 0 evening 17:00–21:00 → gap 6h < 8h.
    rows = [
        _multiday_row(position_id="pos1", name="A", band="morning",
                      window=("07:00", "11:00"), active_days=[0]),
        _multiday_row(position_id="pos2", name="B", band="evening",
                      window=("17:00", "21:00"), active_days=[0]),
    ]
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "21:00"}]})]
    ac = {"pos1:0": [_assign("u1")], "pos2:0": [_assign("u1")]}
    res = compute_board_warnings(_board(rows), ac, pool)
    w = next(w for w in res["by_guard"]["u1"] if w["type"] == "insufficient_rest")
    assert w["gap_hours"] == 6


def test_nine_hour_gap_sufficient_rest():
    rows = [
        _multiday_row(position_id="pos1", name="A", band="morning",
                      window=("07:00", "10:00"), active_days=[0]),
        _multiday_row(position_id="pos2", name="B", band="evening",
                      window=("19:00", "22:00"), active_days=[0]),
    ]
    pool = [_guard("u1", availability={"0": [{"start": "07:00", "end": "22:00"}]})]
    ac = {"pos1:0": [_assign("u1")], "pos2:0": [_assign("u1")]}
    res = compute_board_warnings(_board(rows), ac, pool)
    assert not any(w["type"] == "insufficient_rest" for w in res["by_guard"].get("u1", []))


def test_over_consecutive_days_hard():
    # 7 consecutive days assigned > 6 cap.
    board = _board([_multiday_row(active_days=range(7))])
    pool = [_guard("u1", availability={str(d): [{"start": "07:00", "end": "15:00"}] for d in range(7)})]
    ac = {f"pos1:{d}": [_assign("u1")] for d in range(7)}
    res = compute_board_warnings(board, ac, pool)
    w = next(w for w in res["by_guard"]["u1"] if w["type"] == "over_consecutive_days")
    assert w["days"] == 7


def test_six_consecutive_days_ok():
    board = _board([_multiday_row(active_days=range(6))])
    pool = [_guard("u1", availability={str(d): [{"start": "07:00", "end": "15:00"}] for d in range(6)})]
    ac = {f"pos1:{d}": [_assign("u1")] for d in range(6)}
    res = compute_board_warnings(board, ac, pool)
    assert not any(w["type"] == "over_consecutive_days" for w in res["by_guard"].get("u1", []))


def test_night_continuation_suppresses_false_out_of_availability():
    # Night 23:00–07:00 on day 0 (available), then morning 07:00–09:00 on day 1
    # with NO declared morning availability → continuation, not out_of_availability.
    rows = [
        _multiday_row(position_id="pos1", name="לילה", band="night",
                      window=("23:00", "07:00"), active_days=[0]),
        _multiday_row(position_id="pos2", name="בוקר", band="morning",
                      window=("07:00", "09:00"), active_days=[1]),
    ]
    pool = [_guard("u1", availability={"0": [{"start": "23:00", "end": "07:00"}]})]
    ac = {"pos1:0": [_assign("u1")], "pos2:1": [_assign("u1")]}
    res = compute_board_warnings(_board(rows), ac, pool)
    # No out_of_availability on the morning continuation cell.
    assert "pos2:1" not in res["by_cell"]


def test_valid_full_schedule_total_zero():
    board = _board([_multiday_row(active_days=[0, 2, 4])])
    pool = [_guard("u1", availability={str(d): [{"start": "07:00", "end": "15:00"}] for d in (0, 2, 4)})]
    ac = {f"pos1:{d}": [_assign("u1")] for d in (0, 2, 4)}
    res = compute_board_warnings(board, ac, pool)
    assert res["summary"]["total"] == 0
