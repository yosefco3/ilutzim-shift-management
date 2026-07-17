"""
Bot procedures list — the default procedure leads with a ⭐ marker; the rest
keep newest-first order. Covers ``order_and_mark_procedures`` (pure helper used
by the ``proc:menu`` / ``proc:list`` handlers).
"""

from types import SimpleNamespace

from app.bot.keyboards.procedures import order_and_mark_procedures


def _proc(pid, title, is_default=False):
    return SimpleNamespace(id=pid, title=title, is_default=is_default)


def test_default_procedure_leads_with_star_marker():
    procedures = [
        _proc("a", "נהל א"),
        _proc("b", "נהל ב", is_default=True),
        _proc("c", "נהל ג"),
    ]
    items = order_and_mark_procedures(procedures)
    # default (b) is first, prefixed with ⭐; rest keep their order
    assert items[0] == ("b", "⭐ נהל ב")
    assert items[1] == ("a", "נהל א")
    assert items[2] == ("c", "נהל ג")


def test_no_default_keeps_newest_first_order():
    procedures = [_proc("a", "נהל א"), _proc("b", "נהל ב")]
    items = order_and_mark_procedures(procedures)
    assert items == [("a", "נהל א"), ("b", "נהל ב")]
    # no ⭐ anywhere
    assert all(not label.startswith("⭐") for _, label in items)


def test_empty_list():
    assert order_and_mark_procedures([]) == []
