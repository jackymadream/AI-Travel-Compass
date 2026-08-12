"""Unit tests for CacheService + embedding/POI cache integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.agent_tools import MOCK_CITY_TOKYO, search_pois_tool
from src.services.cache_service import (
    TTL_EMBEDDING_SECONDS,
    TTL_POI_SECONDS,
    CacheService,
    embedding_cache_key,
    hash_cache_key,
    make_cache_key,
    poi_cache_key,
    reset_cache_service,
    search_cache_key,
)
from src.services import rag_service


@pytest.fixture
def memory_cache() -> CacheService:
    cache = CacheService.memory()
    reset_cache_service(cache)
    yield cache
    reset_cache_service(None)


def test_hash_and_key_helpers_are_stable() -> None:
    assert hash_cache_key("food city") == hash_cache_key("food city")
    assert hash_cache_key("a") != hash_cache_key("b")
    assert search_cache_key("quiet sea") == f"search:{hash_cache_key('quiet sea')}"
    assert make_cache_key("search", "quiet sea") == search_cache_key("quiet sea")

    poi_key = poi_cache_key(MOCK_CITY_TOKYO, "food", ["ramen", "market"], 5)
    assert poi_key.startswith(f"poi:{MOCK_CITY_TOKYO}:food:")
    # Preference order must not change the key.
    assert poi_key == poi_cache_key(
        MOCK_CITY_TOKYO, "food", ["market", "ramen"], 5
    )


def test_get_or_set_miss_computes_then_hit_skips_factory(
    memory_cache: CacheService,
) -> None:
    calls = {"n": 0}

    def factory() -> list[float]:
        calls["n"] += 1
        return [0.1, 0.2, 0.3]

    key = embedding_cache_key("cozy food", model="text-embedding-004", dimensions=3)
    first = memory_cache.get_or_set(key, factory, ttl_seconds=TTL_EMBEDDING_SECONDS)
    second = memory_cache.get_or_set(key, factory, ttl_seconds=TTL_EMBEDDING_SECONDS)

    assert first == [0.1, 0.2, 0.3]
    assert second == first
    assert calls["n"] == 1


def test_cache_set_get_roundtrip(memory_cache: CacheService) -> None:
    key = "search:demo"
    assert memory_cache.get(key) is None
    memory_cache.set(key, {"hits": 2}, ttl_seconds=60)
    assert memory_cache.get(key) == {"hits": 2}


def test_poi_search_cache_hit_avoids_recomputation(memory_cache: CacheService) -> None:
    calls = {"n": 0}
    sample = [
        {
            "city_id": MOCK_CITY_TOKYO,
            "name": "Cached Ramen",
            "category": "food",
            "cost_usd": 12.0,
            "duration_minutes": 40,
            "description": "cached",
            "tags": ["food"],
        }
    ]

    def fake_uncached(
        city_id: str,
        category: str,
        preferences: list[str],
        limit: int = 5,
    ) -> list[dict]:
        calls["n"] += 1
        return sample

    with patch(
        "src.services.agent_tools._search_pois_uncached",
        side_effect=fake_uncached,
    ):
        first = search_pois_tool(MOCK_CITY_TOKYO, "food", ["ramen"], limit=3)
        second = search_pois_tool(MOCK_CITY_TOKYO, "food", ["ramen"], limit=3)

    assert first == sample
    assert second == sample
    assert calls["n"] == 1
    # Key should be present with POI TTL path exercised via set.
    key = poi_cache_key(MOCK_CITY_TOKYO, "food", ["ramen"], 3) + ":mock"
    assert memory_cache.get(key) == sample
    assert TTL_POI_SECONDS == 7 * 24 * 60 * 60


def test_embedding_cache_hit_skips_vertex(memory_cache: CacheService) -> None:
    calls = {"n": 0}
    vector = [0.5] * 8

    def fake_compute(cleaned: str, *, dims: int) -> list[float]:
        calls["n"] += 1
        assert dims == 8
        return vector

    with (
        patch.object(rag_service, "_embedding_dimensions", return_value=8),
        patch.object(
            rag_service,
            "_compute_query_embedding",
            side_effect=fake_compute,
        ),
    ):
        first = rag_service.get_query_embedding("  quiet coastal food  ")
        second = rag_service.get_query_embedding("quiet coastal food")

    assert first == vector
    assert second == vector
    assert calls["n"] == 1


def test_from_env_falls_back_to_memory_without_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    service = CacheService.from_env()
    assert service.backend_name == "memory"
    service.set("k", "v", ttl_seconds=10)
    assert service.get("k") == "v"
