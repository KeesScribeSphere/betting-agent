"""Structured logging with secret scrubbing."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

import structlog

SECRET_KEY_PATTERN = re.compile(r"(KEY|SECRET|TOKEN|MNEMONIC|PRIVATE)", re.I)
ETH_PRIVATE_KEY_PATTERN = re.compile(r"\b0x[0-9a-fA-F]{64}\b")


def scrub_secrets(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Remove sensitive values from log event dicts."""
    secrets: set[str] = set()

    for key, value in list(event_dict.items()):
        if SECRET_KEY_PATTERN.search(str(key)) and value is not None:
            event_dict[key] = "***REDACTED***"
            if isinstance(value, str) and len(value) > 8:
                secrets.add(value)
        elif isinstance(value, str):
            if ETH_PRIVATE_KEY_PATTERN.search(value):
                event_dict[key] = "***REDACTED***"
                secrets.add(value)

    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            for secret in secrets:
                if secret and secret in value:
                    event_dict[key] = value.replace(secret, "***REDACTED***")
    return event_dict


def configure_logging(log_path: str | Path | None = None, level: int = logging.INFO) -> None:
    """Configure structlog for JSON lines to stdout and optional file."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True) if log_path else None

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        scrub_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_path:
        file_handler = logging.FileHandler(log_path)
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
