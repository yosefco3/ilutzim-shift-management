"""
Tests for setup_logging level resolution.

Regression guard: production previously hardcoded WARNING, which suppressed
every logger.info() — including the scheduler/bot lifecycle lines — making the
deployment unobservable. An explicit LOG_LEVEL must now win, with a per-env
fallback when it's missing/invalid (and an invalid level must not raise).
"""

import logging

import pytest

from app.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _reset_ilutzim_logger():
    """Each test starts from a clean 'ilutzim' logger."""
    logger = logging.getLogger("ilutzim")
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    yield
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)


@pytest.mark.parametrize(
    "log_level,environment,expected",
    [
        ("INFO", "production", logging.INFO),      # explicit level wins in prod
        ("WARNING", "production", logging.WARNING),
        ("DEBUG", "dev", logging.DEBUG),
        ("BOGUS", "production", logging.WARNING),  # invalid -> env default, no raise
        (None, "production", logging.WARNING),     # missing -> env default
        (None, "staging", logging.INFO),
        (None, "dev", logging.DEBUG),
    ],
)
def test_effective_level(log_level, environment, expected):
    setup_logging(log_level, environment)
    assert logging.getLogger("ilutzim").level == expected


def test_repeat_call_reapplies_level_without_duplicating_handlers():
    setup_logging("WARNING", "production")
    handler_count = len(logging.getLogger("ilutzim").handlers)
    # A second call (e.g. on app reload) must update the level but not stack
    # another console/file handler pair.
    setup_logging("INFO", "production")
    logger = logging.getLogger("ilutzim")
    assert logger.level == logging.INFO
    assert len(logger.handlers) == handler_count
