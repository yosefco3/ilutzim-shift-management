"""Unit tests for lifting guard attributes out of the free-text notes column.

The Stage-A export crams constraining attributes (אחמ"ש / רכב סיור / חמוש) into
the same "הערות" cell as genuine notes. ``split_notes`` separates them so the
board can enforce them and stops raising false "missing attribute" warnings.
"""

from app.constants import UserRole
from app.services.constraints_import.attributes import split_notes


def test_extracts_ahmash_and_patrol_vehicle():
    roles, note = split_notes('אחמ"ש · מוסמך רכב סיור · אחראי משמרת')
    # אחמ"ש and "אחראי משמרת" are the same attribute → one AHMASH.
    assert roles == [UserRole.AHMASH.value, UserRole.PATROL_VEHICLE.value]
    assert note is None


def test_ahras_mishmeret_alias_maps_to_ahmash():
    roles, note = split_notes("אחראי משמרת")
    assert roles == [UserRole.AHMASH.value]
    assert note is None


def test_armed_vs_unarmed_precedence():
    assert split_notes("חמוש")[0] == [UserRole.ARMED.value]
    assert split_notes("לא חמוש")[0] == [UserRole.UNARMED.value]


def test_keeps_genuine_notes_and_extracts_attribute():
    roles, note = split_notes('אחמ"ש · מגיע באיחור בימי שישי')
    assert roles == [UserRole.AHMASH.value]
    assert note == "מגיע באיחור בימי שישי"


def test_plain_note_is_left_untouched():
    roles, note = split_notes("לא עובד בשבת")
    assert roles == []
    assert note == "לא עובד בשבת"


def test_none_and_empty():
    assert split_notes(None) == ([], None)
    assert split_notes("") == ([], "")


def test_deduplicates_repeated_attribute():
    roles, _ = split_notes('אחמ"ש · אחראי משמרת · אחמש')
    assert roles == [UserRole.AHMASH.value]
