"""
Feature flag: PROCEDURES_ENABLED gates the procedure-quiz admin router. When
off, /admin/procedures/* routes are not registered (404); core routes stay.
"""

from app.config import get_settings


def _build_app(monkeypatch, enabled: bool):
    monkeypatch.setenv("PROCEDURES_ENABLED", "true" if enabled else "false")
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    get_settings.cache_clear()  # don't leak the override into other tests
    return app


def _paths(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_procedures_routes_present_when_enabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, True))
    assert any("/admin/procedures" in p for p in paths)
    assert "/admin/procedures/ping" in paths


def test_procedures_routes_absent_when_disabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, False))
    assert not any("/admin/procedures" in p for p in paths)
    # core routes remain
    assert any("/admin/weeks" in p for p in paths)
    assert "/health" in paths


def test_procedures_flag_defaults_off():
    """Fresh settings (no env) must default the flag to False."""
    import os

    saved = os.environ.pop("PROCEDURES_ENABLED", None)
    try:
        from app.config import Settings

        s = Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite:///test.db",
            TELEGRAM_BOT_TOKEN="t",
            APP_URL="http://localhost:3000",
            ADMIN_API_KEY="k",
            JWT_SECRET_KEY="secret-that-is-long-enough-for-validation",
            ENVIRONMENT="dev",
        )
        assert s.PROCEDURES_ENABLED is False
        assert s.ANTHROPIC_API_KEY is None
    finally:
        if saved is not None:
            os.environ["PROCEDURES_ENABLED"] = saved
