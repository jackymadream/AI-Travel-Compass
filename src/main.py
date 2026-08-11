"""GenAI Travel Compass — FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.routers import countries, health, itinerary, search
from src.utils.logger import (
    REQUEST_ID_HEADER,
    clear_trace_id,
    configure_logging,
    get_logger,
    log_event,
    new_trace_id,
    set_trace_id,
)

configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

app = FastAPI(
    title="GenAI Travel Compass",
    version="0.1.0",
    description="Personalized travel recommendations with deterministic filtering + GenAI.",
)

# Default includes local + production custom-domain frontends.
# Override entirely via CORS_ORIGINS (comma-separated) in the environment.
_DEFAULT_CORS_ORIGINS = (
    "https://jackymadream.com,"
    "https://www.jackymadream.com,"
    "http://localhost:3000,"
    "http://127.0.0.1:3000"
)

_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach ``X-Request-ID`` and log request start / status / latency."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        trace_id = incoming or new_trace_id()
        set_trace_id(trace_id)
        started = time.perf_counter()

        log_event(
            logger,
            "request_started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            log_event(
                logger,
                "request_failed",
                level=logging.ERROR,
                duration_ms=duration_ms,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
            )
            clear_trace_id()
            raise
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            response.headers[REQUEST_ID_HEADER] = trace_id
            log_event(
                logger,
                "request_completed",
                duration_ms=duration_ms,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
            )
            clear_trace_id()
            return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
# Last added = outermost: wraps CORS + routes with trace ID + latency logs.
app.add_middleware(RequestIdMiddleware)

app.include_router(health.router)
app.include_router(countries.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(itinerary.router, prefix="/api/v1")