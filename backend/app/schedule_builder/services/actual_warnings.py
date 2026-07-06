"""
Soft warnings for the actual board (step 05).

The actual schedule is edited **freely** — day-of reality outranks any planning
rule, so nothing here blocks. These advisories are recomputed on every board
read (never stored) and rendered as banners/tags:

- ``already_in_shift``            — the guard is placed on two overlapping
                                    windows that day (any positions).
- ``overstaffed_cell``            — more than two guards on a regular
                                    (non-event) cell. Allowed, worth a glance.
- ``assignments_outside_window``  — an assignment that no longer fits its
                                    position's day window (day deactivated or
                                    hours narrowed after the placement). The
                                    assignment is kept; the admin decides.
"""

from app.schedule_builder.utils import intervals as iv


def _resolved_intervals(assignment, window) -> list[tuple[int, int]] | None:
    """Assignment hours on the 07:00-anchored axis, or None when unresolvable."""
    if assignment.segment_start and assignment.segment_end:
        return iv.normalize(assignment.segment_start, assignment.segment_end)
    if window:
        return iv.normalize(window["start"], window["end"])
    return None


def compute_actual_warnings(rows: list[dict], assignments: list) -> list[dict]:
    """Compute the soft advisories for one actual board.

    ``rows`` are board-row dicts (``build_position_row``); ``assignments`` are
    ``ActualAssignment`` rows with ``user`` eager-loaded.
    """
    warnings: list[dict] = []

    # position_id → (name, {day_index: window|None}, is_event)
    pos_info = {
        row["position_id"]: (
            row["name"],
            {c["day_index"]: c["window"] for c in row["cells"]},
            row["is_event"],
        )
        for row in rows
    }

    # ── Per-assignment placement checks + per-(user, day) hour collection ──
    by_user_day: dict[tuple, list[dict]] = {}
    by_cell_count: dict[tuple, int] = {}
    for a in assignments:
        info = pos_info.get(a.actual_position_id)
        if info is None:  # structurally unexpected; nothing useful to say
            continue
        name, windows, is_event = info
        window = windows.get(a.day_index)
        user_name = a.user.full_name if a.user else ""

        if window is None:
            warnings.append({
                "type": "assignments_outside_window",
                "day_index": a.day_index,
                "position_id": str(a.actual_position_id),
                "position_name": name,
                "user_id": str(a.user_id),
                "user_name": user_name,
                "reason": "inactive_day",
            })
        elif a.segment_start and a.segment_end:
            seg = iv.normalize(a.segment_start, a.segment_end)
            win = iv.normalize(window["start"], window["end"])
            if iv.subtract(seg, win):
                warnings.append({
                    "type": "assignments_outside_window",
                    "day_index": a.day_index,
                    "position_id": str(a.actual_position_id),
                    "position_name": name,
                    "user_id": str(a.user_id),
                    "user_name": user_name,
                    "reason": "segment_outside_window",
                })

        spans = _resolved_intervals(a, window)
        if spans is not None:
            by_user_day.setdefault((a.user_id, a.day_index), []).append({
                "position_id": a.actual_position_id,
                "position_name": name,
                "user_name": user_name,
                "spans": spans,
            })

        if not is_event:
            key = (a.actual_position_id, a.day_index)
            by_cell_count[key] = by_cell_count.get(key, 0) + 1

    # ── already_in_shift: overlapping hours of the same guard in one day ──
    for (user_id, day_index), entries in by_user_day.items():
        flagged = False
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if iv.intersect(entries[i]["spans"], entries[j]["spans"]):
                    warnings.append({
                        "type": "already_in_shift",
                        "day_index": day_index,
                        "user_id": str(user_id),
                        "user_name": entries[i]["user_name"],
                        "position_names": sorted({
                            entries[i]["position_name"],
                            entries[j]["position_name"],
                        }),
                    })
                    flagged = True
                    break
            if flagged:
                break

    # ── overstaffed_cell: >2 guards on a regular cell ──
    for (position_id, day_index), count in by_cell_count.items():
        if count > 2:
            name = pos_info[position_id][0]
            warnings.append({
                "type": "overstaffed_cell",
                "day_index": day_index,
                "position_id": str(position_id),
                "position_name": name,
                "count": count,
            })

    return warnings
