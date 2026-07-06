"""Helper for building the guard WebApp ("/submit") URL.

Centralises the URL so the cache-busting ``v`` parameter (see ``app.version``)
is always appended consistently — whether the link is a WebApp button, a plain
URL button, or a fallback text link.
"""

from app.version import APP_VERSION


def submit_webapp_url(tg_id: int | str | None = None) -> str:
    """Return the guard constraints WebApp URL with a cache-busting version.

    Args:
        tg_id: optional Telegram user id to embed as ``tg_id`` (used by /start).
    """
    # Imported lazily (matching the bot keyboards) so the current settings object
    # is read at call time — keeps the URL correct under test patching.
    from app.config import settings

    params = []
    if tg_id is not None:
        params.append(f"tg_id={tg_id}")
    params.append(f"v={APP_VERSION}")
    return f"{settings.APP_URL}/submit?" + "&".join(params)
