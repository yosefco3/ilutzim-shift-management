"""
Interval math on the security-day timeline (part B, task 06).

The security day runs **07:00 → 07:00** the next morning, in HH:MM strings. All
math happens in **minutes-from-07:00** (0 = 07:00 … 1440 = 07:00 next day). A
window whose ``end <= start`` wraps past midnight (e.g. ``23:00–07:00`` →
``[960, 1440]``).

THE UNION RULE (the whole point of this module): availability/coverage hours are
the duration of the **union** of windows, never their sum — overlapping windows
are merged *before* measuring:

    07:00–16:30 ∪ 15:00–19:00 = 07:00–19:00 = 12h  (not 13.5h)

Functions are pure and operate on ``(start_min, end_min)`` tuples or HH:MM
strings, so the rule is unit-tested here rather than in a service.
"""

DAY_MINUTES = 24 * 60  # 1440
_ANCHOR = 7 * 60  # 07:00 — start of the security day


def to_min(hhmm: str) -> int:
    """'HH:MM' → minutes-from-07:00 in [0, 1440)."""
    hours, minutes = hhmm.split(":")
    return (int(hours) * 60 + int(minutes) - _ANCHOR) % DAY_MINUTES


def normalize(start: str, end: str) -> list[tuple[int, int]]:
    """A window 'HH:MM'→'HH:MM' as 1–2 sub-intervals within [0, 1440].

    A window that wraps past the 07:00 anchor is split into two linear pieces so
    downstream set-math stays on a simple [0, 1440] axis. A full-day window
    (start == end) covers the whole security day.
    """
    s = to_min(start)
    e = to_min(end)
    if s == e:
        return [(0, DAY_MINUTES)]  # whole day (e.g. 07:00–07:00)
    if e > s:
        return [(s, e)]
    # Wraps the anchor; drop the second piece when it is zero-length (ends 07:00).
    return [(s, DAY_MINUTES)] if e == 0 else [(s, DAY_MINUTES), (0, e)]


def merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent intervals into a sorted disjoint list."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    out = [ordered[0]]
    for s, e in ordered[1:]:
        last_s, last_e = out[-1]
        if s <= last_e:  # overlap or touch
            out[-1] = (last_s, max(last_e, e))
        else:
            out.append((s, e))
    return out


def duration(intervals: list[tuple[int, int]]) -> int:
    """Total minutes covered by a list of intervals (union — merges first)."""
    return sum(e - s for s, e in merge(intervals))


def intersect(
    window: list[tuple[int, int]], avail: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """The parts of ``window`` that fall inside ``avail`` (both pre-mergeable)."""
    w = merge(window)
    a = merge(avail)
    out = []
    for ws, we in w:
        for as_, ae in a:
            lo, hi = max(ws, as_), min(we, ae)
            if lo < hi:
                out.append((lo, hi))
    return merge(out)


def subtract(
    window: list[tuple[int, int]], avail: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """The parts of ``window`` NOT inside ``avail`` (the uncovered gaps)."""
    w = merge(window)
    a = merge(avail)
    out = []
    for ws, we in w:
        cursor = ws
        for as_, ae in a:
            if ae <= cursor or as_ >= we:
                continue
            if as_ > cursor:
                out.append((cursor, min(as_, we)))
            cursor = max(cursor, ae)
            if cursor >= we:
                break
        if cursor < we:
            out.append((cursor, we))
    return out


def coverage(window_start: str, window_end: str, avail: list[tuple[int, int]]) -> dict:
    """Classify how an availability set covers a position window.

    Returns ``{"state": "full"|"partial"|"none", "gaps": [(s, e), …]}`` where
    ``gaps`` are the uncovered sub-intervals (empty when full).
    """
    window = normalize(window_start, window_end)
    covered = duration(intersect(window, avail))
    total = duration(window)
    if covered == 0:
        return {"state": "none", "gaps": merge(window)}
    if covered >= total:
        return {"state": "full", "gaps": []}
    return {"state": "partial", "gaps": subtract(window, avail)}


def to_hhmm(minute: int) -> str:
    """minutes-from-07:00 → 'HH:MM' (1440 wraps back to 07:00)."""
    absolute = (minute + _ANCHOR) % DAY_MINUTES
    return f"{absolute // 60:02d}:{absolute % 60:02d}"
