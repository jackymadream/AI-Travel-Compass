"""
Structured JSON logging for GenAI Travel Compass (Phase 4).

Log fields: timestamp, level, message, trace_id, duration_ms, metadata.
Trace IDs propagate via contextvars (set by Request ID middleware).
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"

_CONFIGURED = False


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_trace_id(trace_id: str | None) -> None:
    _trace_id.set(trace_id)


def clear_trace_id() -> None:
    _trace_id.set(None)


def new_trace_id() -> str:
    return str(uuid.uuid4())


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        metadata = getattr(record, "metadata", None)
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, dict):
            metadata = {"value": metadata}

        duration_ms = getattr(record, "duration_ms", None)
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or get_trace_id(),
            "duration_ms": duration_ms,
            "metadata": metadata,
        }
        if record.exc_info:
            payload["metadata"] = {
                **metadata,
                "exception": self.formatException(record.exc_info),
            }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, level: int | str = logging.INFO, stream: Any = None) -> None:
    """Configure root logging for JSON stdout (idempotent)."""
    global _CONFIGURED
    root = logging.getLogger()
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    # Replace handlers so tests / reloads get a single JSON formatter.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; ensure JSON config is applied once."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    duration_ms: float | None = None,
    **metadata: Any,
) -> None:
    """
    Emit a structured log line with optional duration and metadata dict.

    Example::
        log_event(logger, "cache_hit", cache_key=key, duration_ms=0.4)
    """
    logger.log(
        level,
        message,
        extra={
            "duration_ms": duration_ms,
            "metadata": metadata,
            "trace_id": get_trace_id(),
        },
    )


class elapsed_timer:
    """Context manager measuring wall time in milliseconds."""

    def __init__(self) -> None:
        self.start = 0.0
        self.duration_ms = 0.0

    def __enter__(self) -> elapsed_timer:
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.duration_ms = round((time.perf_counter() - self.start) * 1000, 3)
