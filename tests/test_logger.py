"""Tests for JSON structured logging and request/trace ID propagation."""

from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.utils.logger import (
    REQUEST_ID_HEADER,
    JsonLogFormatter,
    clear_trace_id,
    configure_logging,
    get_logger,
    get_trace_id,
    log_event,
    set_trace_id,
)


@pytest.fixture
def json_log_stream() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(level=logging.INFO, stream=stream)
    clear_trace_id()
    yield stream
    clear_trace_id()


def _parse_lines(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_json_logger_output_fields(json_log_stream: io.StringIO) -> None:
    set_trace_id("trace-abc-123")
    logger = get_logger("test.logger")
    log_event(
        logger,
        "embedding_cache_hit",
        duration_ms=1.5,
        cache_key="embed:deadbeef",
        backend="memory",
    )

    records = _parse_lines(json_log_stream)
    assert records
    payload = records[-1]
    assert payload["level"] == "INFO"
    assert payload["message"] == "embedding_cache_hit"
    assert payload["trace_id"] == "trace-abc-123"
    assert payload["duration_ms"] == 1.5
    assert payload["metadata"]["cache_key"] == "embed:deadbeef"
    assert payload["metadata"]["backend"] == "memory"
    assert "timestamp" in payload


def test_trace_id_propagates_across_log_calls(json_log_stream: io.StringIO) -> None:
    set_trace_id("shared-trace")
    logger = get_logger("test.propagation")
    log_event(logger, "first", step=1)
    assert get_trace_id() == "shared-trace"
    log_event(logger, "second", duration_ms=12.0, step=2)

    records = _parse_lines(json_log_stream)
    assert len(records) >= 2
    assert records[-2]["trace_id"] == "shared-trace"
    assert records[-1]["trace_id"] == "shared-trace"
    assert records[-1]["duration_ms"] == 12.0
    assert records[-1]["metadata"]["step"] == 2


def test_json_formatter_includes_null_optional_fields() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello"
    assert payload["duration_ms"] is None
    assert payload["metadata"] == {}


def test_request_id_middleware_sets_and_echoes_header() -> None:
    from src.main import app

    with TestClient(app) as client:
        response = client.get(
            "/health/liveness",
            headers={REQUEST_ID_HEADER: "client-req-42"},
        )

    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER) == "client-req-42"


def test_request_id_middleware_generates_id_when_missing() -> None:
    from src.main import app

    with TestClient(app) as client:
        response = client.get("/health/liveness")

    assert response.status_code == 200
    generated = response.headers.get(REQUEST_ID_HEADER)
    assert generated
    assert len(generated) >= 8
