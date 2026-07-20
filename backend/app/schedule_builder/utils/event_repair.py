"""Pure planning logic for repairing event flags lost by the old duplicate bug.

Before the fix, ``ProfileService._copy_positions`` dropped ``is_event`` and
``event_required_count`` when duplicating a profile, so every "לא מפוצל" (event)
position of a copy became an ordinary splitting one. This module decides, given
the base profile's event positions, which same-named positions in OTHER profiles
need their event shape restored — matched by name (the only stable identity
across a duplicate). It touches no database; the ops script wraps it with I/O so
the decision can be unit-tested in isolation.
"""

from dataclasses import dataclass
from typing import Iterable, Protocol


class _PositionRow(Protocol):
    """The shape the planner reads — a DB row or any object with these attrs."""

    profile_name: str
    id: object
    name: str
    is_event: bool
    event_required_count: int | None


@dataclass(frozen=True)
class RepairItem:
    """One position to restore: set ``is_event=True`` and write ``set_count``."""

    profile_name: str
    position_id: object
    position_name: str
    set_count: int | None


def build_repair_plan(
    base_events: dict[str, int | None],
    candidates: Iterable[_PositionRow],
) -> list[RepairItem]:
    """Return the positions whose event shape must be restored.

    ``base_events`` maps a base event position's ``name`` → its
    ``event_required_count``. ``candidates`` are positions from every OTHER
    profile (never the base). A candidate is repaired when its name matches a
    base event AND it is currently NOT an event. The count comes from the base,
    but only when the candidate has none — a real count on the candidate is
    never overwritten. Already-event and unmatched positions are left out.
    """
    plan: list[RepairItem] = []
    for pos in candidates:
        if pos.name not in base_events:
            continue  # not an event in the base → nothing to restore
        if pos.is_event:
            continue  # already correct
        # Restore from the base, but keep any real count the candidate still has.
        set_count = (
            pos.event_required_count
            if pos.event_required_count is not None
            else base_events[pos.name]
        )
        plan.append(
            RepairItem(
                profile_name=pos.profile_name,
                position_id=pos.id,
                position_name=pos.name,
                set_count=set_count,
            )
        )
    return plan
