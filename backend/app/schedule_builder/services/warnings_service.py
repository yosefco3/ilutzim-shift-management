"""
Canonical soft-warning engine for the schedule builder.

This is a faithful 1:1 port of the client-side engine in
``frontend/admin/src/utils/warnings.js`` (``computeBoardWarnings``). The auto-fill
algorithm needs *exactly* the same rules to rank suggestions, so the rules live
here canonically and the JS copy is kept for live drag-time feedback. The two are
locked together by a shared golden-fixture parity test — a threshold changed in
one language and not the other turns that test red.

Field-name convention: this engine is snake_case (``by_cell`` / ``guard_id`` /
``other_position`` / ``gap_hours``) and the policy keys are snake
(``rest_minutes`` …). The JS engine emits camelCase; the board/pool/assignment
*inputs* are snake_case in both (they come from the snake_case API). The parity
test carries a thin camel↔snake adapter on the JS side only — the engines
themselves are never adapted.

All time math goes through ``app/schedule_builder/utils/intervals.py`` (the 07:00
security-day axis); nothing here re-derives the anchor.
"""

from app.schedule_builder.utils import intervals as iv

DAY_MINUTES = 24 * 60

# Policy thresholds (locked with the user, 2026-06-29). Mirrors WARNING_POLICY in
# warnings.js — same values, snake keys.
WARNING_POLICY = {
    "rest_minutes": 8 * 60,             # 480 — min rest between two work blocks
    "max_consecutive_days": 6,          # max consecutive assigned days
    "max_continuous_minutes": 12 * 60,  # 720 — max length of one continuous block
}

# 'hard' (red) vs 'soft' (orange) — same split as warnings.js.
WARNING_SEVERITY = {
    "out_of_availability": "hard",
    "missing_attribute": "hard",
    "double_booking": "hard",
    "insufficient_rest": "hard",
    "over_continuous_hours": "hard",
    "over_consecutive_days": "hard",
    "partial_coverage": "soft",
    "already_in_shift": "soft",
    "understaffed_event": "soft",
}


def _lower(s) -> str:
    return str(s).lower()


def _effective_window(assignment: dict, cell: dict) -> dict | None:
    """The window actually worked in a cell: explicit segment, else cell window."""
    if assignment.get("segment_start") and assignment.get("segment_end"):
        return {"start": assignment["segment_start"], "end": assignment["segment_end"]}
    return cell.get("window") or None


def _windows_overlap(a: dict, b: dict) -> bool:
    """Do two 'HH:MM'→'HH:MM' windows overlap on the security-day axis?"""
    ai = iv.normalize(a["start"], a["end"])
    bi = iv.normalize(b["start"], b["end"])
    for as_, ae in ai:
        for bs, be in bi:
            if max(as_, bs) < min(ae, be):
                return True
    return False


def _longest_consecutive_run(days) -> int:
    """Longest run of consecutive day indices in a set (e.g. [0,1,2,4] → 3)."""
    best = 0
    run = 0
    prev = None
    for d in sorted(set(days)):
        run = run + 1 if prev is not None and d == prev + 1 else 1
        if run > best:
            best = run
        prev = d
    return best


def _coverage(win_start: str, win_end: str, day_windows: list) -> dict:
    """Coverage of a position window by a guard's day-availability.

    Mirrors ``coverage`` in intervals.js: availability windows are normalized and
    merged, then classified full/partial/none, with ``gaps`` as ``{start, end}``
    HH:MM objects (empty unless partial)."""
    avail = iv.merge(
        [p for w in (day_windows or []) for p in iv.normalize(w["start"], w["end"])]
    )
    cov = iv.coverage(win_start, win_end, avail)
    if cov["state"] == "partial":
        gaps = [{"start": iv.to_hhmm(s), "end": iv.to_hhmm(e)} for s, e in cov["gaps"]]
    else:
        gaps = []
    return {"state": cov["state"], "gaps": gaps}


def compute_board_warnings(
    board: dict,
    assignments_by_cell: dict | None = None,
    pool: list | None = None,
    policy: dict = WARNING_POLICY,
) -> dict:
    """Derive every soft warning for a built board.

    Returns ``{"by_cell", "by_guard", "summary"}`` — structurally identical to the
    JS ``computeBoardWarnings`` (snake keys). ``by_cell`` is keyed
    ``"<position_id>:<day_index>"``; ``by_guard`` by guard id; ``summary`` counts
    each occurrence per type plus a ``total``.
    """
    assignments_by_cell = assignments_by_cell or {}
    pool = pool or []
    by_cell: dict[str, list] = {}
    by_guard: dict[str, list] = {}
    pool_by_id = {g["id"]: g for g in pool}
    # Per-guard placements, for the cross-cell rules below (insertion-ordered).
    guard_items: dict = {}

    def push_cell(key, w):
        by_cell.setdefault(key, []).append(w)

    def push_guard(gid, w):
        by_guard.setdefault(gid, []).append(w)

    # ── Night-shift continuation (pre-pass) ──────────────────────────────────
    # A guard who works a shift ending exactly at the 07:00 anchor on day d may
    # keep working continuously into day d+1's early morning — one unbroken shift
    # — for up to ``max_continuous_minutes`` from that night's start. The forms cap
    # availability at 07:00, so that morning placement has no declared coverage and
    # would otherwise look ``out_of_availability``. Record the per-guard, per-day
    # continuation ceiling so the coverage check can skip that one false warning.
    # The 12h ceiling is still enforced by over_continuous_hours; a real break
    # still trips insufficient_rest.
    cont_cap_by_guard_day: dict = {}  # gid → {continuation_day: cap_min_from_anchor}
    for row in board.get("rows") or []:
        for cell in row.get("cells") or []:
            if not cell.get("active"):
                continue
            for a in assignments_by_cell.get(f"{row['position_id']}:{cell['day_index']}") or []:
                win = _effective_window(a, cell)
                if not win:
                    continue
                start_min = iv.to_min(win["start"])
                # Ends exactly at the anchor (07:00 → 0) and starts later in the
                # security day → a night shift butting up against the boundary.
                if iv.to_min(win["end"]) != 0 or start_min == 0:
                    continue
                cap = start_min - (DAY_MINUTES - policy["max_continuous_minutes"])
                cont_day = cell["day_index"] + 1
                if cap <= 0 or cont_day > 6:
                    continue
                per_day = cont_cap_by_guard_day.setdefault(a["user_id"], {})
                per_day[cont_day] = max(per_day.get(cont_day, 0), cap)

    def _is_night_continuation(gid, win, day_index) -> bool:
        """Is this cell window a legitimate continuous continuation of the guard's
        night shift — starting at the anchor (adjacent, no gap) and ending within
        the 12h ceiling? Only then is out-of-availability a false alarm."""
        cap = cont_cap_by_guard_day.get(gid, {}).get(day_index)
        if not cap:
            return False
        ivs = iv.normalize(win["start"], win["end"])
        return len(ivs) == 1 and ivs[0][0] == 0 and ivs[0][1] <= cap

    for row in board.get("rows") or []:
        # An event (non-splitting) position has no coverage notion — guards attend
        # the whole window together — so no availability/partial warnings.
        is_event = bool(row.get("is_event"))
        required_count = row.get("event_required_count") if is_event else None
        for cell in row.get("cells") or []:
            if not cell.get("active"):
                continue
            key = f"{row['position_id']}:{cell['day_index']}"
            assigns = assignments_by_cell.get(key) or []
            # A happening fixed-count event day (≥1 guard) short of its count.
            if required_count and 1 <= len(assigns) < required_count:
                push_cell(key, {
                    "type": "understaffed_event",
                    "need": required_count,
                    "have": len(assigns),
                })
            # Empty active cells are surfaced by the board "ריק" stat, not here.
            if not assigns:
                continue
            for a in assigns:
                guard = pool_by_id.get(a.get("user_id"))
                guard_name = (
                    a.get("user_full_name")
                    or (guard.get("full_name") if guard else "")
                    or ""
                )
                win = _effective_window(a, cell)

                # Coverage vs the guard's availability that day.
                if not is_event and guard and win:
                    day_windows = (guard.get("availability") or {}).get(
                        str(cell["day_index"])
                    ) or []
                    cov = _coverage(win["start"], win["end"], day_windows)
                    # A night shift that continues, unbroken and within 12h, into
                    # this morning is legitimate even with no declared morning
                    # availability — don't flag it out-of-availability / partial.
                    if cov["state"] != "full" and _is_night_continuation(
                        a["user_id"], win, cell["day_index"]
                    ):
                        pass  # intentionally no warning
                    elif cov["state"] == "none":
                        push_cell(key, {
                            "type": "out_of_availability",
                            "guard_id": a["user_id"],
                            "guard_name": guard_name,
                        })
                    elif cov["state"] == "partial":
                        push_cell(key, {
                            "type": "partial_coverage",
                            "guard_id": a["user_id"],
                            "guard_name": guard_name,
                            "gaps": cov["gaps"],
                        })

                # Required attribute the guard lacks (case-insensitive).
                held = {
                    _lower(r)
                    for r in (a.get("user_roles") or (guard.get("roles") if guard else None) or [])
                }
                missing = [
                    k for k in (row.get("required_attributes") or [])
                    if _lower(k) not in held
                ]
                if missing:
                    push_cell(key, {
                        "type": "missing_attribute",
                        "guard_id": a["user_id"],
                        "guard_name": guard_name,
                        "missing": missing,
                    })

                if win:
                    guard_items.setdefault(a["user_id"], []).append({
                        "key": key,
                        "day_index": cell["day_index"],
                        "window": win,
                        "position_name": row.get("name"),
                        "guard_name": guard_name,
                        "band": row.get("band"),
                    })

    # Cross-cell rules, per guard.
    for gid, items in guard_items.items():
        guard_name = items[0]["guard_name"] if items else ""

        # double_booking — same guard, same day, overlapping windows.
        by_day: dict = {}
        for it in items:
            by_day.setdefault(it["day_index"], []).append(it)
        for day_items in by_day.values():
            for i in range(len(day_items)):
                for j in range(i + 1, len(day_items)):
                    if _windows_overlap(day_items[i]["window"], day_items[j]["window"]):
                        push_cell(day_items[i]["key"], {
                            "type": "double_booking",
                            "guard_id": gid,
                            "guard_name": guard_name,
                            "other_position": day_items[j]["position_name"],
                        })
                        push_cell(day_items[j]["key"], {
                            "type": "double_booking",
                            "guard_id": gid,
                            "guard_name": guard_name,
                            "other_position": day_items[i]["position_name"],
                        })

        # already_in_shift — same guard in 2+ cells of one shift (band) on one day.
        by_shift: dict = {}
        for it in items:
            by_shift.setdefault(f"{it['day_index']}:{it['band']}", []).append(it)
        for shift_items in by_shift.values():
            if len(shift_items) < 2:
                continue
            for it in shift_items:
                push_cell(it["key"], {
                    "type": "already_in_shift",
                    "guard_id": gid,
                    "guard_name": guard_name,
                })

        # Build a week-long timeline of work intervals (absolute minutes from the
        # week's 07:00 anchor) and merge into continuous work blocks, tracking
        # which cells feed each block. The security day already absorbs the
        # midnight rollover, so day d's intervals live in [d*1440, (d+1)*1440].
        tagged = []
        for it in items:
            for s, e in iv.normalize(it["window"]["start"], it["window"]["end"]):
                tagged.append({
                    "s": it["day_index"] * DAY_MINUTES + s,
                    "e": it["day_index"] * DAY_MINUTES + e,
                    "key": it["key"],
                })
        tagged.sort(key=lambda t: (t["s"], t["e"]))

        blocks: list = []
        for t in tagged:
            last = blocks[-1] if blocks else None
            if last and t["s"] <= last["e"]:
                last["e"] = max(last["e"], t["e"])
                if t["key"] not in last["keys"]:
                    last["keys"].append(t["key"])
            else:
                blocks.append({"s": t["s"], "e": t["e"], "keys": [t["key"]]})

        # over_continuous_hours — a single block longer than the cap.
        for b in blocks:
            if b["e"] - b["s"] > policy["max_continuous_minutes"]:
                push_guard(gid, {
                    "type": "over_continuous_hours",
                    "guard_id": gid,
                    "guard_name": guard_name,
                    "hours": (b["e"] - b["s"]) / 60,
                    "cells": list(b["keys"]),
                })

        # insufficient_rest — gap between two consecutive blocks below the minimum.
        for i in range(1, len(blocks)):
            gap = blocks[i]["s"] - blocks[i - 1]["e"]
            if 0 < gap < policy["rest_minutes"]:
                push_guard(gid, {
                    "type": "insufficient_rest",
                    "guard_id": gid,
                    "guard_name": guard_name,
                    "gap_hours": gap / 60,
                    "cells": list(blocks[i - 1]["keys"]) + list(blocks[i]["keys"]),
                })

        # over_consecutive_days — too many consecutive assigned days.
        run = _longest_consecutive_run([it["day_index"] for it in items])
        if run > policy["max_consecutive_days"]:
            push_guard(gid, {
                "type": "over_consecutive_days",
                "guard_id": gid,
                "guard_name": guard_name,
                "days": run,
            })

    # Summary counts (each per-cell occurrence and each per-guard warning count 1).
    summary = {"total": 0}

    def bump(t):
        summary[t] = summary.get(t, 0) + 1
        summary["total"] += 1

    for lst in by_cell.values():
        for w in lst:
            bump(w["type"])
    for lst in by_guard.values():
        for w in lst:
            bump(w["type"])

    return {"by_cell": by_cell, "by_guard": by_guard, "summary": summary}
