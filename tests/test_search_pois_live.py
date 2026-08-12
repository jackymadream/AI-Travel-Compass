"""Unit tests for Phase 5.2 live POI search (Qdrant → Supabase fallback)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from src.tools import search_pois as poi_mod


def test_search_pois_uses_qdrant_when_hits_present() -> None:
    fake_hits = [
        {
            "city_id": "city-1",
            "name": "Vector Temple",
            "category": "attraction",
            "cost_usd": 5,
            "duration_minutes": 90,
            "description": "From Qdrant",
            "tags": ["temple", "culture"],
            "rating": 4.5,
            "safety_score": 5,
            "score": 0.9,
        }
    ]

    with (
        patch.object(poi_mod, "embed_query", return_value=[0.1] * 8),
        patch.object(poi_mod, "get_qdrant_client", return_value=MagicMock()),
        patch.object(poi_mod, "search_poi_vectors", return_value=fake_hits) as mock_search,
        patch.object(poi_mod, "_search_supabase") as mock_db,
    ):
        results = poi_mod.search_pois_uncached(
            city_id="city-1",
            category="attraction",
            preferences=["temple"],
            limit=5,
            min_safety_score=3,
            min_rating=4.0,
        )

    mock_search.assert_called_once()
    kwargs = mock_search.call_args.kwargs
    assert kwargs["city_id"] == "city-1"
    assert kwargs["category"] == "attraction"
    assert kwargs["min_safety_score"] == 3
    assert kwargs["min_rating"] == 4.0
    mock_db.assert_not_called()
    assert len(results) == 1
    assert results[0]["name"] == "Vector Temple"
    assert results[0]["cost_usd"] == 5.0


def test_search_pois_falls_back_to_supabase_when_qdrant_empty() -> None:
    db_row = {
        "city_id": "city-1",
        "name": "SQL Cafe",
        "category": "food",
        "description": "From Supabase",
        "tags": ["cafe"],
        "cost_usd": 12,
        "duration_minutes": 45,
        "rating": 4.2,
        "safety_score": 4,
    }

    with (
        patch.object(poi_mod, "embed_query", return_value=[0.2] * 8),
        patch.object(poi_mod, "get_qdrant_client", return_value=MagicMock()),
        patch.object(poi_mod, "search_poi_vectors", return_value=[]),
        patch.object(poi_mod, "_search_supabase", return_value=[
            poi_mod._normalize_poi(db_row, city_id="city-1", category="food")
        ]) as mock_db,
    ):
        results = poi_mod.search_pois_uncached(
            city_id="city-1",
            category="food",
            preferences=["cafe"],
            limit=3,
        )

    mock_db.assert_called_once()
    assert results[0]["name"] == "SQL Cafe"


def test_search_pois_qdrant_error_falls_back_to_supabase() -> None:
    with (
        patch.object(poi_mod, "embed_query", side_effect=RuntimeError("vertex down")),
        patch.object(
            poi_mod,
            "_search_supabase",
            return_value=[
                {
                    "city_id": "c",
                    "name": "Park Rest",
                    "category": "rest",
                    "cost_usd": 0.0,
                    "duration_minutes": 60,
                    "description": "Quiet",
                    "tags": ["park"],
                    "rating": None,
                    "safety_score": 4,
                    "lat": None,
                    "lon": None,
                }
            ],
        ),
    ):
        results = poi_mod.search_pois_uncached("c", "rest", [], limit=2)

    assert results and results[0]["name"] == "Park Rest"
