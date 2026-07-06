"""
Feature flag: SCHEDULE_BUILDER_ENABLED gates the Part-B routers (schedule
builder + constraints import). When off, those routes are not registered at all.
"""

from app.config import get_settings


def _build_app(monkeypatch, enabled: bool):
    monkeypatch.setenv("SCHEDULE_BUILDER_ENABLED", "true" if enabled else "false")
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    get_settings.cache_clear()  # don't leak the override into other tests
    return app


def _paths(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_builder_routes_present_when_enabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, True))
    assert any("/admin/builder" in p for p in paths)
    assert any("/admin/import/constraints" in p for p in paths)


def test_builder_routes_absent_when_disabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, False))
    assert not any("/admin/builder" in p for p in paths)
    assert not any("/admin/import/constraints" in p for p in paths)
    # Core (part-A) routes remain registered.
    assert any("/admin/weeks" in p for p in paths)
    assert "/health" in paths
