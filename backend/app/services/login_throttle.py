"""
LoginThrottle — minimal in-memory brute-force protection for admin login.

Per-process only (a plain dict): suitable for the single-process deployment
described in the runbook. If the backend ever runs multiple workers, move this
state to a shared store (DB/Redis) so the counters are not reset per worker.

The clock is injectable (``time_fn``) so tests can simulate the passage of time
without sleeping.
"""

import logging
import math
import time
from dataclasses import dataclass

logger = logging.getLogger("ilutzim")


@dataclass
class _Entry:
    count: int = 0
    window_start: float = 0.0
    locked_until: float = 0.0


class LoginThrottle:
    """Tracks failed login attempts per identity and enforces a temporary lock."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 900,
        lockout_seconds: int = 900,
        time_fn=time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._time = time_fn
        self._entries: dict[str, _Entry] = {}

    @staticmethod
    def _key(raw: str) -> str:
        return (raw or "").strip().lower()

    def seconds_until_unlock(self, raw: str) -> int:
        """Remaining lock time in seconds (0 if not locked)."""
        entry = self._entries.get(self._key(raw))
        if entry is None:
            return 0
        remaining = entry.locked_until - self._time()
        return int(math.ceil(remaining)) if remaining > 0 else 0

    def minutes_until_unlock(self, raw: str) -> int:
        """Remaining lock time rounded up to whole minutes (>=1 while locked)."""
        seconds = self.seconds_until_unlock(raw)
        return max(1, math.ceil(seconds / 60)) if seconds > 0 else 0

    def is_locked(self, raw: str) -> bool:
        return self.seconds_until_unlock(raw) > 0

    def record_failure(self, raw: str) -> None:
        """Increment the failure counter; lock the identity once the limit is hit."""
        key = self._key(raw)
        now = self._time()
        entry = self._entries.get(key)
        # Start a fresh window if there is none, the window has elapsed, or a
        # previous lock has expired (so the user gets a clean slate).
        if (
            entry is None
            or now - entry.window_start > self._window
            or (entry.locked_until and now >= entry.locked_until)
        ):
            entry = _Entry(count=0, window_start=now)
            self._entries[key] = entry

        entry.count += 1
        if entry.count >= self._max:
            entry.locked_until = now + self._lockout
            logger.warning(
                "Admin login locked after %d failed attempts: %s", entry.count, key
            )

    def reset(self, raw: str) -> None:
        """Clear the counter for an identity (called on successful login)."""
        self._entries.pop(self._key(raw), None)

    def clear(self) -> None:
        """Wipe all state (used by tests)."""
        self._entries.clear()


_throttle: LoginThrottle | None = None


def get_login_throttle() -> LoginThrottle:
    """Return the process-wide login throttle, built from settings on first use."""
    global _throttle
    if _throttle is None:
        from app.config import get_settings

        s = get_settings()
        _throttle = LoginThrottle(
            max_attempts=s.MAX_LOGIN_ATTEMPTS,
            window_seconds=s.LOGIN_ATTEMPT_WINDOW_MINUTES * 60,
            lockout_seconds=s.LOGIN_LOCKOUT_MINUTES * 60,
        )
    return _throttle
