"""
Request rate limiting (Phase 5.2).

Unauthenticated clients: 15 search requests / minute (SlowAPI).
Uses Redis when ``REDIS_URL`` is set; otherwise in-memory storage.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

SEARCH_RATE_LIMIT = os.getenv("SEARCH_RATE_LIMIT", "15/minute").strip() or "15/minute"


def _storage_uri() -> str:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        return redis_url
    return "memory://"


def get_remote_address_key(request) -> str:  # type: ignore[no-untyped-def]
    """Prefer ``X-Forwarded-For`` (Cloud Run / Vercel) then peer IP."""
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_remote_address_key,
    storage_uri=_storage_uri(),
    headers_enabled=False,
)
