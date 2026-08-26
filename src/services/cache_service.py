"""
Cache service with Redis primary store and in-memory fallback.

Phase 4 — used by embedding lookups and POI tool results.
When Redis is unreachable or unset, callers still get a working TTL cache locally.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default TTLs (seconds).
TTL_EMBEDDING_SECONDS = 24 * 60 * 60  # 24 hours — query embeddings
TTL_POI_SECONDS = 7 * 24 * 60 * 60  # 7 days — POI search results
TTL_SEARCH_SECONDS = 24 * 60 * 60  # optional NL search payload cache

_ROOT_ENV_LOADED = False


def _load_env() -> None:
    global _ROOT_ENV_LOADED
    if _ROOT_ENV_LOADED:
        return
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / ".env")
    _ROOT_ENV_LOADED = True


def hash_cache_key(*parts: Any, length: int = 16) -> str:
    """Stable short hash for cache key segments (query text, prefs, etc.)."""
    material = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return digest[: max(8, length)]


def make_cache_key(namespace: str, *parts: Any) -> str:
    """
    Build a namespaced cache key.

    Examples:
      search:{hash(query_text)} → make_cache_key("search", query_text)
      poi:{city_id}:{category}  → poi_cache_key(...)
    """
    ns = (namespace or "cache").strip().lower()
    return f"{ns}:{hash_cache_key(*parts)}"


def embedding_cache_key(query_text: str, *, model: str, dimensions: int) -> str:
    return f"embed:{hash_cache_key(model, dimensions, (query_text or '').strip())}"


def poi_cache_key(
    city_id: str,
    category: str,
    preferences: list[str] | None = None,
    limit: int = 5,
) -> str:
    prefs = ",".join(sorted((p or "").strip().lower() for p in (preferences or []) if p))
    cat = (category or "").strip().lower()
    return f"poi:{city_id}:{cat}:{hash_cache_key(prefs, limit)}"


def search_cache_key(query_text: str) -> str:
    return f"search:{hash_cache_key((query_text or '').strip())}"


class InMemoryCacheBackend:
    """Process-local TTL dict — used when Redis is unavailable."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at is not None and time.time() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int | None) -> None:
        expires_at: float | None = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            doomed = [key for key in self._store if key.startswith(prefix)]
            for key in doomed:
                self._store.pop(key, None)
            return len(doomed)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class RedisCacheBackend:
    """Thin Redis string get/set wrapper."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> str | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    def set(self, key: str, value: str, ttl_seconds: int | None) -> None:
        if ttl_seconds is not None and ttl_seconds > 0:
            self._client.setex(key, int(ttl_seconds), value)
        else:
            self._client.set(key, value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        keys = list(self._client.scan_iter(match=f"{prefix}*"))
        if not keys:
            return 0
        self._client.delete(*keys)
        return len(keys)

    def clear(self) -> None:
        # Intentionally not FLUSHDB — too dangerous for shared Redis.
        raise NotImplementedError("Redis clear() is disabled; delete keys explicitly.")


class CacheService:
    """JSON get/set cache with Redis or in-memory backend."""

    def __init__(
        self,
        backend: InMemoryCacheBackend | RedisCacheBackend,
        *,
        backend_name: str = "memory",
    ) -> None:
        self._backend = backend
        self.backend_name = backend_name

    @classmethod
    def from_env(cls) -> CacheService:
        """Prefer Redis when ``REDIS_URL`` connects; otherwise in-memory."""
        _load_env()
        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            logger.info("REDIS_URL unset — using in-memory cache backend")
            return cls(InMemoryCacheBackend(), backend_name="memory")

        try:
            import redis
        except ImportError:
            logger.warning(
                "redis package not installed — using in-memory cache backend"
            )
            return cls(InMemoryCacheBackend(), backend_name="memory")

        try:
            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            client.ping()
            logger.info("Connected to Redis cache at REDIS_URL")
            return cls(RedisCacheBackend(client), backend_name="redis")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Redis unavailable (%s) — falling back to in-memory cache",
                exc,
            )
            return cls(InMemoryCacheBackend(), backend_name="memory")

    @classmethod
    def memory(cls) -> CacheService:
        """Explicit in-memory instance (tests / local)."""
        return cls(InMemoryCacheBackend(), backend_name="memory")

    def get(self, key: str) -> Any | None:
        raw = self._backend.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Corrupt cache value for key=%s — treating as miss", key)
            return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self._backend.set(key, payload, ttl_seconds)

    def delete(self, key: str) -> None:
        self._backend.delete(key)

    def clear(self) -> None:
        clearer = getattr(self._backend, "clear", None)
        if callable(clearer):
            clearer()

    def delete_prefix(self, prefix: str) -> int:
        deleter = getattr(self._backend, "delete_prefix", None)
        if callable(deleter):
            return int(deleter(prefix))
        return 0

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        """
        Return cached value on hit; otherwise run ``factory``, store, and return.

        Cache hits avoid re-computation of ``factory``.
        """
        cached = self.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value


_cache_singleton: CacheService | None = None
_cache_lock = threading.Lock()


def get_cache_service() -> CacheService:
    """Process-wide cache singleton (Redis or memory)."""
    global _cache_singleton
    if _cache_singleton is None:
        with _cache_lock:
            if _cache_singleton is None:
                _cache_singleton = CacheService.from_env()
    return _cache_singleton


def reset_cache_service(service: CacheService | None = None) -> None:
    """Replace or clear the singleton (tests)."""
    global _cache_singleton
    with _cache_lock:
        _cache_singleton = service


def invalidate_poi_cache(city_id: str) -> int:
    """Delete cached POI search results for a city across categories/preferences."""
    if not city_id:
        return 0
    return get_cache_service().delete_prefix(f"poi:{city_id}:")
