"""
Stage 3 / 01 step 4 — punch flow: geo, PunchService (dedup + radius), handlers.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.attendance.constants import PunchDirection, PunchSource
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.punch_service import PunchService
from app.attendance.utils.geo import haversine_m
from app.bot.handlers.attendance import (
    PunchFlow,
    on_punch_button,
    on_punch_cancel,
    on_punch_location,
    on_punch_not_location,
)
from app.bot.keyboards.attendance import (
    BTN_PUNCH_IN,
    BTN_PUNCH_OUT,
    location_request_kb,
    punch_reply_kb,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository

SITE = (31.778000, 35.235000)  # Jerusalem-ish


def _config(site=True, radius=150) -> AttendanceConfig:
    return AttendanceConfig(
        grace_minutes=15,
        big_gap_minutes=60,
        site_lat=SITE[0] if site else None,
        site_lng=SITE[1] if site else None,
        site_radius_m=radius,
        admin_alerts_enabled=False,
        admin_chat_id="",
        company_name="ספרא",
    )


async def _make_guard(db_session, telegram_id="111222333", consent=True) -> User:
    user = User(
        phone_number="0501234567",
        first_name="יוסי",
        last_name="כהן",
        roles=[],
        telegram_id=telegram_id,
        gps_consent_at=datetime(2026, 7, 1, 8, 0) if consent else None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------- geo ----------

def test_haversine_known_values():
    assert haversine_m(*SITE, *SITE) == pytest.approx(0.0, abs=0.01)
    # ~111.19 km per degree of latitude
    assert haversine_m(31.0, 35.0, 32.0, 35.0) == pytest.approx(111_195, rel=0.01)
    # small offset ≈ 100m
    assert haversine_m(31.778, 35.235, 31.7789, 35.235) == pytest.approx(100, rel=0.05)


# ---------- PunchService ----------

@pytest.mark.asyncio
async def test_record_punch_inside_radius(db_session):
    guard = await _make_guard(db_session)
    service = PunchService(AttendanceEventRepository(db_session), _config())

    outcome = await service.record_punch(
        guard.id,
        PunchDirection.IN,
        datetime(2026, 7, 5, 7, 0),
        lat=SITE[0] + 0.0005,  # ~55m north
        lng=SITE[1],
    )
    assert outcome.created is True
    assert outcome.event.out_of_radius is False
    assert outcome.event.distance_from_site_m == pytest.approx(55, rel=0.1)
    assert outcome.event.source == PunchSource.TELEGRAM


@pytest.mark.asyncio
async def test_record_punch_outside_radius_marks_but_records(db_session):
    guard = await _make_guard(db_session)
    service = PunchService(AttendanceEventRepository(db_session), _config())

    outcome = await service.record_punch(
        guard.id,
        PunchDirection.IN,
        datetime(2026, 7, 5, 7, 0),
        lat=SITE[0] + 0.02,  # ~2.2km away
        lng=SITE[1],
    )
    assert outcome.created is True  # never blocked
    assert outcome.event.out_of_radius is True
    assert outcome.event.distance_from_site_m > 1000


@pytest.mark.asyncio
async def test_record_punch_without_site_config_skips_radius(db_session):
    guard = await _make_guard(db_session)
    service = PunchService(
        AttendanceEventRepository(db_session), _config(site=False)
    )
    outcome = await service.record_punch(
        guard.id, PunchDirection.IN, datetime(2026, 7, 5, 7, 0), lat=31.0, lng=35.0
    )
    assert outcome.event.distance_from_site_m is None
    assert outcome.event.out_of_radius is None


@pytest.mark.asyncio
async def test_double_tap_dedup(db_session):
    guard = await _make_guard(db_session)
    service = PunchService(AttendanceEventRepository(db_session), _config())
    first = await service.record_punch(
        guard.id, PunchDirection.IN, datetime(2026, 7, 5, 7, 0)
    )
    dup = await service.record_punch(
        guard.id, PunchDirection.IN, datetime(2026, 7, 5, 7, 3)
    )
    assert dup.created is False
    assert dup.event.id == first.event.id

    # opposite direction is NOT a duplicate
    out = await service.record_punch(
        guard.id, PunchDirection.OUT, datetime(2026, 7, 5, 7, 4)
    )
    assert out.created is True


# ---------- router registration order ----------

def test_attendance_router_registered_before_fallback(monkeypatch):
    """The attendance router must precede main_router, whose catch-all
    "לא הבנתי" handler would otherwise swallow the punch-button messages."""
    from app.config import get_settings

    monkeypatch.setenv("ATTENDANCE_ENABLED", "true")
    get_settings.cache_clear()
    import app.bot.bot_router as bot_router_mod
    from app.bot.core import router as main_router
    from app.bot.handlers.attendance import router as attendance_router

    def _detach():
        # aiogram routers may belong to ONE dispatcher; detach so other tests
        # (and a prior test's dispatcher) can rebuild without "already attached".
        attendance_router._parent_router = None
        main_router._parent_router = None

    bot_router_mod._dispatcher = None
    _detach()
    try:
        dp = bot_router_mod.get_dispatcher()
        subs = list(dp.sub_routers)
        assert subs.index(attendance_router) < subs.index(main_router)
    finally:
        bot_router_mod._dispatcher = None
        _detach()
        get_settings.cache_clear()


# ---------- keyboards ----------

def test_punch_keyboards_shape():
    kb = punch_reply_kb()
    texts = [b.text for row in kb.keyboard for b in row]
    assert BTN_PUNCH_IN in texts and BTN_PUNCH_OUT in texts
    assert kb.is_persistent is True

    loc = location_request_kb()
    assert loc.keyboard[0][0].request_location is True


# ---------- handlers ----------

def _message(text=None, telegram_id=111222333, location=None):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=telegram_id),
        location=location,
        answer=AsyncMock(),
    )


def _state():
    store = {}

    async def set_state(s):
        store["state"] = s

    async def update_data(**kw):
        store.update(kw)

    async def get_data():
        return dict(store)

    async def clear():
        store.clear()

    return SimpleNamespace(
        set_state=AsyncMock(side_effect=set_state),
        update_data=AsyncMock(side_effect=update_data),
        get_data=AsyncMock(side_effect=get_data),
        clear=AsyncMock(side_effect=clear),
        _store=store,
    )


def _fake_user_session(db_session):
    async def fake():
        shim = SimpleNamespace(commit=db_session.commit, close=AsyncMock())
        return UserRepository(db_session), shim

    return fake


def _fake_punch_services(db_session, config=None):
    async def fake():
        shim = SimpleNamespace(commit=db_session.commit, close=AsyncMock())
        events_repo = AttendanceEventRepository(db_session)
        service = PunchService(events_repo, config or _config())
        from app.attendance.repositories.shift_repository import (
            AttendanceShiftRepository,
        )
        from app.attendance.services.pairing_service import PairingService

        pairing = PairingService(events_repo, AttendanceShiftRepository(db_session))
        return UserRepository(db_session), service, pairing, shim

    return fake


@pytest.mark.asyncio
async def test_punch_button_without_consent_shows_consent(db_session):
    await _make_guard(db_session, consent=False)
    message = _message(text=BTN_PUNCH_IN)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    # consent message sent, no FSM state set
    state.set_state.assert_not_awaited()
    args, kwargs = message.answer.await_args
    assert "שיתוף מיקום" in args[0]
    assert kwargs.get("reply_markup") is not None


async def _open_shift(db_session, guard, at=datetime(2026, 7, 5, 7, 0)):
    """Create an IN punch + recompute so the guard has an OPEN shift."""
    from app.attendance.repositories.shift_repository import AttendanceShiftRepository
    from app.attendance.services.pairing_service import PairingService

    repo = AttendanceEventRepository(db_session)
    await repo.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=at,
        source=PunchSource.TELEGRAM,
    )
    pairing = PairingService(repo, AttendanceShiftRepository(db_session))
    await pairing.recompute_user(
        guard.id, at.date(), at.date(), now=at + timedelta(hours=1)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_punch_in_with_no_open_shift_requests_location(db_session):
    """The matching case — no confirmation prompt, straight to location."""
    await _make_guard(db_session)
    message = _message(text=BTN_PUNCH_IN)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    state.set_state.assert_awaited_once_with(PunchFlow.waiting_for_location)
    assert state._store["punch_direction"] == "in"
    args, _ = message.answer.await_args
    assert "כניסה" in args[0]


@pytest.mark.asyncio
async def test_punch_out_with_open_shift_requests_location(db_session):
    """OUT while on shift is the expected flow — no prompt."""
    guard = await _make_guard(db_session)
    await _open_shift(db_session, guard)
    message = _message(text=BTN_PUNCH_OUT)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    state.set_state.assert_awaited_once_with(PunchFlow.waiting_for_location)
    assert state._store["punch_direction"] == "out"


@pytest.mark.asyncio
async def test_punch_in_while_on_shift_asks_did_you_mean_out(db_session):
    guard = await _make_guard(db_session)
    await _open_shift(db_session, guard)
    message = _message(text=BTN_PUNCH_IN)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    state.set_state.assert_not_awaited()  # no location flow yet
    args, kwargs = message.answer.await_args
    assert "אתה כבר במשמרת" in args[0]
    assert "07:00" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    assert kb[0][0].callback_data == "att_dir:out"   # suggested fix first
    assert kb[1][0].callback_data == "att_dir:in"
    assert kb[2][0].callback_data == "att_dir_cancel"


@pytest.mark.asyncio
async def test_punch_out_without_open_shift_asks_did_you_mean_in(db_session):
    await _make_guard(db_session)
    message = _message(text=BTN_PUNCH_OUT)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    state.set_state.assert_not_awaited()
    args, kwargs = message.answer.await_args
    assert "לא רשומה לך כניסה" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "att_dir:in"


def _dir_callback(data, telegram_id=111222333):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=telegram_id),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_direction_confirm_callback_starts_location_flow(db_session):
    await _make_guard(db_session)
    from app.bot.handlers.attendance import on_direction_confirmed

    callback = _dir_callback("att_dir:out")
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_direction_confirmed(callback, state)

    state.set_state.assert_awaited_once_with(PunchFlow.waiting_for_location)
    assert state._store["punch_direction"] == "out"
    args, _ = callback.message.answer.await_args
    assert "שתף מיקום" in args[0]


@pytest.mark.asyncio
async def test_direction_cancel_callback(db_session):
    from app.bot.handlers.attendance import on_direction_cancelled

    callback = _dir_callback("att_dir_cancel")
    state = _state()
    await on_direction_cancelled(callback, state)

    state.clear.assert_awaited()
    args, _ = callback.message.answer.await_args
    assert "בוטלה" in args[0]


@pytest.mark.asyncio
async def test_punch_button_double_tap_skips_location_request(db_session):
    """A recent same-direction punch → immediate 'already recorded', no
    location share is requested and no FSM state is entered."""
    guard = await _make_guard(db_session)
    from app.utils.date_utils import now_il

    service = PunchService(AttendanceEventRepository(db_session), _config())
    await service.record_punch(
        guard.id, PunchDirection.IN, now_il().replace(tzinfo=None)
    )
    await db_session.commit()

    message = _message(text=BTN_PUNCH_IN)
    state = _state()
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_button(message, state)

    state.set_state.assert_not_awaited()
    args, kwargs = message.answer.await_args
    assert "כבר נרשמה כניסה" in args[0]
    assert "שתף מיקום" not in args[0]


@pytest.mark.asyncio
async def test_location_creates_event_and_confirms(db_session):
    guard = await _make_guard(db_session)
    state = _state()
    state._store["punch_direction"] = "in"
    message = _message(
        location=SimpleNamespace(
            latitude=SITE[0], longitude=SITE[1], horizontal_accuracy=10.0
        )
    )
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_location(message, state)

    events = await AttendanceEventRepository(db_session).list_for_user(
        guard.id, datetime(2000, 1, 1), datetime(2100, 1, 1)
    )
    assert len(events) == 1
    assert events[0].direction == PunchDirection.IN
    assert events[0].out_of_radius is False
    args, _ = message.answer.await_args
    assert "✅ נרשמה כניסה" in args[0]


@pytest.mark.asyncio
async def test_location_double_tap_says_already_recorded(db_session):
    guard = await _make_guard(db_session)
    repo = AttendanceEventRepository(db_session)
    service = PunchService(repo, _config())
    from app.utils.date_utils import now_il

    await service.record_punch(
        guard.id, PunchDirection.IN, now_il().replace(tzinfo=None)
    )
    await db_session.commit()

    state = _state()
    state._store["punch_direction"] = "in"
    message = _message(
        location=SimpleNamespace(latitude=SITE[0], longitude=SITE[1])
    )
    with patch(
        "app.bot.handlers.attendance._get_punch_services",
        side_effect=_fake_punch_services(db_session),
    ):
        await on_punch_location(message, state)

    events = await repo.list_for_user(guard.id, datetime(2000, 1, 1), datetime(2100, 1, 1))
    assert len(events) == 1  # no duplicate appended
    args, _ = message.answer.await_args
    assert "כבר נרשמה" in args[0]


@pytest.mark.asyncio
async def test_cancel_and_text_instead_of_location(db_session):
    state = _state()
    message = _message(text="סתם טקסט")
    await on_punch_not_location(message)
    args, kwargs = message.answer.await_args
    assert "לשתף מיקום" in args[0]

    cancel_msg = _message(text="❌ ביטול")
    await on_punch_cancel(cancel_msg, state)
    state.clear.assert_awaited()
    args, _ = cancel_msg.answer.await_args
    assert "בוטלה" in args[0]
