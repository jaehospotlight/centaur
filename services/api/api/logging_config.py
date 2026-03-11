"""Shared structlog configuration for API and CLI."""

from __future__ import annotations

import os
import sys

import structlog

_LOG_LEVELS = {"critical": 50, "error": 40, "warning": 30, "info": 20, "debug": 10}


def configure_structlog() -> int:
    """Configure structlog with JSON (prod) or console (dev) rendering.

    Returns the resolved log level integer.
    """
    log_level = _LOG_LEVELS.get(
        (os.getenv("AI_V2_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "info").lower(), 20
    )
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
    )
    return log_level
