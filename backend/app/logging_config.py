"""
Structured logging setup with JSON format and log rotation.
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(log_level: str, environment: str) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR).
        environment: Deployment environment (dev, staging, production).
    """
    logger = logging.getLogger("ilutzim")

    # Honour an explicit LOG_LEVEL when it names a valid level; only fall back
    # to a per-environment default when it doesn't. Previously production was
    # hardcoded to WARNING, which silently hid every logger.info() — including
    # the scheduler/bot lifecycle lines (Scheduled auto_open_job, Telegram bot
    # started, ...) — leaving prod unobservable. Computed before the handler
    # check so a repeated call still re-applies the level (and an invalid
    # LOG_LEVEL no longer raises).
    requested = logging.getLevelName(log_level.upper()) if log_level else None
    if isinstance(requested, int):
        effective_level = requested
    elif environment == "production":
        effective_level = logging.WARNING
    elif environment == "staging":
        effective_level = logging.INFO
    else:
        effective_level = logging.DEBUG

    logger.setLevel(effective_level)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return

    # Console handler with JSON output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(console_handler)

    # File handler with rotation (10 MB, keep 5 backups)
    try:
        file_handler = RotatingFileHandler(
            "ilutzim.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        logger.addHandler(file_handler)
    except OSError:
        # If file logging fails, continue with console only
        pass

    # Reduce noise from third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the 'ilutzim' namespace.

    Usage::

        from app.logging_config import get_logger
        logger = get_logger(__name__)   # → ilutzim.app.repositories.user_repository
    """
    base = "ilutzim"
    full_name = f"{base}.{name}" if name else base
    return logging.getLogger(full_name)
