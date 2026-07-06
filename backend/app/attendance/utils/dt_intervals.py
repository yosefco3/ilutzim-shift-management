"""
Interval math over real datetimes (attendance comparison).

Same algorithms as ``app.schedule_builder.utils.intervals`` but on absolute
``(datetime, datetime)`` pairs instead of the 07:00-anchored HH:MM axis — the
attendance comparison spans real multi-day timelines (night shifts, month
ranges) where an anchored 1440-minute axis would wrap ambiguously.
"""

from datetime import datetime

Interval = tuple[datetime, datetime]


def merge(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping/touching intervals into a sorted disjoint list."""
    out: list[Interval] = []
    for s, e in sorted(i for i in intervals if i[0] < i[1]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """The parts of ``a`` that fall inside ``b``."""
    a, b = merge(a), merge(b)
    out: list[Interval] = []
    for as_, ae in a:
        for bs, be in b:
            lo, hi = max(as_, bs), min(ae, be)
            if lo < hi:
                out.append((lo, hi))
    return merge(out)


def subtract(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """The parts of ``a`` NOT inside ``b``."""
    a, b = merge(a), merge(b)
    out: list[Interval] = []
    for as_, ae in a:
        cursor = as_
        for bs, be in b:
            if be <= cursor or bs >= ae:
                continue
            if bs > cursor:
                out.append((cursor, min(bs, ae)))
            cursor = max(cursor, be)
            if cursor >= ae:
                break
        if cursor < ae:
            out.append((cursor, ae))
    return out


def total_minutes(intervals: list[Interval]) -> int:
    """Union duration in whole minutes."""
    return int(sum((e - s).total_seconds() for s, e in merge(intervals)) // 60)
