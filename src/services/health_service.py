"""Dependency health probes for Redis, Qdrant, and Supabase."""

from __future__ import annotations

import os
from typing import Any, Callable, Literal

from dotenv import load_dotenv

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

CheckStatus = Literal["ok", "unavailable", "skipped"]


def _load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def check_redis() -> dict[str, Any]:
    """
    Probe Redis when ``REDIS_URL`` is set; otherwise report in-memory fallback as ok.
    """
    _load_env()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return {
            "status": "ok",
            "backend": "memory",
            "detail": "REDIS_URL unset; using in-memory cache",
        }

    try:
        import redis
    except ImportError:
        return {
            "status": "unavailable",
            "backend": "redis",
            "detail": "redis package not installed",
        }

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        client.ping()
        return {
            "status": "ok",
            "backend": "redis",
            "detail": "ping ok",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "backend": "redis",
            "detail": str(exc),
        }


def check_vector_db() -> dict[str, Any]:
    """Probe Qdrant connectivity via collection listing."""
    _load_env()
    url = os.getenv("QDRANT_URL", "").strip()
    if not url:
        return {
            "status": "unavailable",
            "detail": "QDRANT_URL is not set",
        }

    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        return {
            "status": "unavailable",
            "detail": "qdrant-client not installed",
        }

    try:
        client = QdrantClient(url=url, api_key=api_key, timeout=5)
        collections = client.get_collections()
        names = [c.name for c in getattr(collections, "collections", [])]
        return {
            "status": "ok",
            "detail": f"reachable; {len(names)} collection(s)",
            "collections": names,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "detail": str(exc),
        }


def check_database() -> dict[str, Any]:
    """Probe Supabase/Postgres with a lightweight countries select."""
    _load_env()
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return {
            "status": "unavailable",
            "detail": "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
        }

    try:
        from supabase import create_client

        client = create_client(url, key)
        result = (
            client.table("countries")
            .select("id")
            .limit(1)
            .execute()
        )
        _ = result.data
        return {
            "status": "ok",
            "detail": "countries query ok",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "detail": str(exc),
        }


Checker = Callable[[], dict[str, Any]]


def build_health_report(
    *,
    redis_checker: Checker = check_redis,
    vector_checker: Checker = check_vector_db,
    database_checker: Checker = check_database,
) -> dict[str, Any]:
    """
    Aggregate dependency checks.

    Overall ``status`` is ``ok`` only when redis, vector_db, and database are ``ok``.
    """
    checks = {
        "redis": redis_checker(),
        "vector_db": vector_checker(),
        "database": database_checker(),
    }
    all_ok = all(checks[name].get("status") == "ok" for name in checks)
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }
