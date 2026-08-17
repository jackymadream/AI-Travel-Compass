"""
Real POI search tool — Qdrant ``travel_pois`` + Supabase ``pois`` fallback.

Used by the itinerary agent (Phase 5.2). Keeps the Phase 3 return contract:
name, category, cost_usd, duration_minutes, description (+ city_id, tags).
"""

from __future__ import annotations

import os
from typing import Any

from src.services.cache_service import (
    TTL_POI_SECONDS,
    get_cache_service,
    poi_cache_key,
)
from src.services.embedding import EmbeddingServiceError, embed_query
from src.services.itinerary_i18n import category_photo
from src.services.qdrant_service import (
    POIS_COLLECTION,
    QdrantServiceError,
    get_qdrant_client,
    search_poi_vectors,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_COST_BY_CATEGORY = {"attraction": 12.0, "food": 18.0, "rest": 8.0}
DEFAULT_DURATION_BY_CATEGORY = {"attraction": 90, "food": 60, "rest": 60}


def search_pois(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
    *,
    min_safety_score: int | None = None,
    min_rating: float | None = None,
) -> list[dict]:
    """
    Public tool entry: cache → Qdrant vector search → Supabase SQL fallback.

    Preference text is embedded with ``text-embedding-004`` (RETRIEVAL_QUERY)
    and used to rank ``travel_pois`` filtered by ``city_id`` + ``category``.
    """
    cache = get_cache_service()
    cache_key = poi_cache_key(city_id, category, preferences, limit)
    if min_safety_score is not None or min_rating is not None:
        cache_key = (
            f"{cache_key}:s{min_safety_score or 0}:r{min_rating or 0}"
        )
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    results = search_pois_uncached(
        city_id,
        category,
        preferences,
        limit,
        min_safety_score=min_safety_score,
        min_rating=min_rating,
    )
    cache.set(cache_key, results, ttl_seconds=TTL_POI_SECONDS)
    return results


def search_pois_uncached(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
    *,
    min_safety_score: int | None = None,
    min_rating: float | None = None,
) -> list[dict]:
    """Live lookup without cache (tests may call or patch this)."""
    category_norm = (category or "").strip().lower()
    prefs = [p.strip() for p in preferences if p and str(p).strip()]
    lim = max(0, int(limit))
    if lim == 0 or not city_id or not category_norm:
        return []

    vector_hits = _search_qdrant(
        city_id=city_id,
        category=category_norm,
        preferences=prefs,
        limit=lim,
        min_safety_score=min_safety_score,
        min_rating=min_rating,
    )
    if vector_hits:
        return vector_hits

    logger.info(
        "POI vector search empty for city_id=%s category=%s; trying Supabase",
        city_id,
        category_norm,
    )
    return _search_supabase(
        city_id=city_id,
        category=category_norm,
        preferences=prefs,
        limit=lim,
        min_safety_score=min_safety_score,
        min_rating=min_rating,
    )


def _preference_query(preferences: list[str], category: str) -> str:
    if preferences:
        return f"{category} " + " ".join(preferences)
    return f"{category} travel points of interest"


def _search_qdrant(
    *,
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int,
    min_safety_score: int | None,
    min_rating: float | None,
) -> list[dict]:
    try:
        query_text = _preference_query(preferences, category)
        vector = embed_query(query_text)
        hits = search_poi_vectors(
            query_vector=vector,
            city_id=city_id,
            category=category,
            limit=max(limit * 2, limit),
            min_safety_score=min_safety_score,
            min_rating=min_rating,
            client=get_qdrant_client(),
        )
    except (EmbeddingServiceError, QdrantServiceError, Exception) as exc:  # noqa: BLE001
        logger.warning("Qdrant POI search failed: %s", exc)
        return []

    results = [_normalize_poi(h, city_id=city_id, category=category) for h in hits]
    # Re-rank lightly by preference token overlap, then truncate.
    scored = [
        (_preference_score(r, [p.lower() for p in preferences]), r) for r in results
    ]
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [r for _, r in scored[:limit]]


def _search_supabase(
    *,
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int,
    min_safety_score: int | None,
    min_rating: float | None,
) -> list[dict]:
    try:
        from src.deps import get_supabase

        supabase = get_supabase()
        query = (
            supabase.table("pois")
            .select(
                "id, city_id, name, category, description, tags, cost_usd, "
                "duration_minutes, price_level, rating, safety_score, "
                "latitude, longitude, address, photo_url"
            )
            .eq("city_id", city_id)
            .eq("category", category)
            .eq("is_active", True)
        )
        if min_safety_score is not None:
            query = query.gte("safety_score", int(min_safety_score))
        if min_rating is not None:
            query = query.gte("rating", float(min_rating))
        response = query.limit(max(limit * 3, limit)).execute()
        rows = response.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Supabase POI fallback failed: %s", exc)
        return []

    prefs = [p.lower() for p in preferences]
    scored: list[tuple[int, dict]] = []
    for row in rows:
        poi = _normalize_poi(row, city_id=city_id, category=category)
        scored.append((_preference_score(poi, prefs), poi))
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [p for _, p in scored[:limit]]


def _normalize_poi(
    raw: dict[str, Any],
    *,
    city_id: str,
    category: str,
) -> dict:
    cat = str(raw.get("category") or category).strip().lower()
    cost = raw.get("cost_usd")
    if cost is None:
        cost = DEFAULT_COST_BY_CATEGORY.get(cat, 15.0)
    duration = raw.get("duration_minutes")
    if duration is None:
        duration = DEFAULT_DURATION_BY_CATEGORY.get(cat, 60)
    tags_raw = raw.get("tags") or []
    tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    name = str(raw.get("name") or "Unknown POI").strip()
    description = str(raw.get("description") or name).strip()
    return {
        "city_id": str(raw.get("city_id") or city_id),
        "id": str(raw["id"]) if raw.get("id") else (str(raw["poi_id"]) if raw.get("poi_id") else None),
        "name": name,
        "category": cat,
        "cost_usd": float(cost),
        "duration_minutes": int(duration),
        "description": description,
        "tags": tags,
        "rating": float(raw["rating"]) if raw.get("rating") is not None else None,
        "safety_score": int(raw["safety_score"])
        if raw.get("safety_score") is not None
        else None,
        "lat": raw.get("lat", raw.get("latitude")),
        "lon": raw.get("lon", raw.get("longitude")),
        "address": raw.get("address"),
        "city": raw.get("city"),
        "photo_url": raw.get("photo_url")
        or category_photo(
            cat,
            hash(name) % 4,
            city=str(raw.get("city") or "") or None,
            poi_name=name,
        ),
    }


def _preference_score(poi: dict[str, Any], preferences: list[str]) -> int:
    if not preferences:
        return 0
    haystack = " ".join(
        [
            poi.get("name", ""),
            poi.get("description", ""),
            " ".join(poi.get("tags") or []),
        ]
    ).lower()
    return sum(1 for pref in preferences if pref in haystack)


def use_mock_pois() -> bool:
    """When true, agent_tools keeps the in-memory mock dataset."""
    return os.getenv("USE_MOCK_POIS", "").strip().lower() in {"1", "true", "yes"}
