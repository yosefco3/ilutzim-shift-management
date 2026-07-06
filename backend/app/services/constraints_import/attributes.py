"""Pull structured guard-attributes (``UserRole``) out of free-text notes.

Stage-A exports cram a guard's *constraining attributes* — אחמ"ש / רכב סיור /
חמוש — into the single "הערות" (notes) column, mixed with genuine notes. These
are constraining factors: a position may require אחמ"ש or רכב סיור, and only a
guard who holds that attribute may fill it. This module lifts the recognised
attribute tokens into ``UserRole`` values so the board can enforce them, and
returns the remaining text as the real note.

אחמ"ש and "אחראי משמרת" are the same attribute (shift supervisor) → ``AHMASH``.
"""

from __future__ import annotations

import re

from app.constants import UserRole

# Tokens in the notes column are separated by middots, bullets, commas, etc.
_SEP_RE = re.compile(r"[·•,;|/\n\r]+")

# Strip Hebrew gershayim/geresh and quotes so אחמ"ש == אחמש for matching.
_QUOTES = str.maketrans("", "", "\"'׳״‘’")


def _canon(segment: str) -> str:
    """Lower-noise form of a token: quotes stripped, whitespace collapsed."""
    return " ".join(segment.translate(_QUOTES).split())


def _match(segment: str) -> str | None:
    """Map a single notes token to a ``UserRole`` value, or None if it's a note."""
    t = _canon(segment)
    if not t:
        return None
    # אחמ"ש and "אחראי משמרת" are the same attribute (shift supervisor).
    if "אחראי משמרת" in t or t.startswith("אחמ") or "אחמש" in t:
        return UserRole.AHMASH.value
    if "סיור" in t:  # "רכב סיור" / "מוסמך רכב סיור"
        return UserRole.PATROL_VEHICLE.value
    if "לא חמוש" in t:
        return UserRole.UNARMED.value
    if "חמוש" in t:
        return UserRole.ARMED.value
    return None


def split_notes(notes: str | None) -> tuple[list[str], str | None]:
    """Split free-text notes into ``(attribute roles, residual note text)``.

    Recognised attribute tokens become ``UserRole`` values (de-duplicated, in
    first-seen order); everything else is rejoined (with " · ") as the note.
    Returns ``([], notes)`` unchanged when there's nothing to extract.
    """
    if not notes:
        return [], notes
    roles: list[str] = []
    kept: list[str] = []
    for segment in _SEP_RE.split(notes):
        token = segment.strip()
        if not token:
            continue
        role = _match(token)
        if role is not None:
            if role not in roles:
                roles.append(role)
        else:
            kept.append(token)
    cleaned = " · ".join(kept) if kept else None
    return roles, cleaned
