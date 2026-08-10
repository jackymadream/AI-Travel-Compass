"""Unit tests for SearchService ranking / formatting (no live Supabase/Qdrant)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.schemas.country import Locale
from src.schemas.search import SearchRequest
from src.services.search_service import SearchService


@pytest.mark.asyncio
async def test_rank_results_localizes_and_scores() -> None:
    service = SearchService(supabase=MagicMock())
    candidates = [
        {
            "city_id": "11111111-1111-1111-1111-111111111111",
            "country_id": "22222222-2222-2222-2222-222222222222",
            "iso_code": "JP",
            "name": {"en": "Tokyo", "zh-HK": "東京", "ja": "東京"},
            "description": {
                "en": "Neon capital",
                "zh-HK": "霓虹首都",
                "ja": "ネオンの首都",
            },
            "safety_index": 5,
            "avg_daily_cost_usd": 130.0,
            "tags": ["food", "culture"],
            "region_tags": ["East Asia"],
        }
    ]
    vector_hits = [
        {
            "city_id": "11111111-1111-1111-1111-111111111111",
            "vector_score": 0.9,
            "score": 0.9,
        }
    ]

    hits = await service.rank_results(
        candidates=candidates,
        vector_hits=vector_hits,
        tags=["food"],
        locale=Locale.ZH_HK,
        limit=5,
    )

    assert len(hits) == 1
    assert hits[0].name == "東京"
    assert hits[0].description == "霓虹首都"
    assert hits[0].tags == ["food"]
    assert hits[0].vector_score == pytest.approx(0.9)
    assert hits[0].score > 0


@pytest.mark.asyncio
async def test_sql_filter_applies_budget_safety_tags() -> None:
    supabase = MagicMock()
    query = MagicMock()
    supabase.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.lte.return_value = query
    query.gte.return_value = query
    query.overlaps.return_value = query
    query.order.return_value = query

    result = MagicMock()
    result.data = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "country_id": "22222222-2222-2222-2222-222222222222",
            "slug": "tokyo",
            "name": {"en": "Tokyo", "zh-HK": "東京", "ja": "東京"},
            "description": {"en": "Neon", "zh-HK": "霓虹", "ja": "ネオン"},
            "safety_index": 5,
            "avg_daily_cost_usd": 130,
            "tags": ["food", "urban"],
            "is_active": True,
            "countries": {
                "id": "22222222-2222-2222-2222-222222222222",
                "iso_code": "JP",
                "name": {"en": "Japan", "zh-HK": "日本", "ja": "日本"},
                "region_tags": ["East Asia"],
                "is_active": True,
            },
        }
    ]
    query.execute.return_value = result

    service = SearchService(supabase=supabase)
    rows = await service.sql_filter_candidates(
        {"max_budget": 150, "min_safety": 4, "tags": ["food"]}
    )

    query.lte.assert_called()
    query.gte.assert_called()
    query.overlaps.assert_called()
    assert len(rows) == 1
    assert rows[0]["iso_code"] == "JP"
    assert rows[0]["city_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_search_empty_candidates_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SearchService(supabase=MagicMock())

    async def empty_candidates(_filters: dict) -> list:
        return []

    monkeypatch.setattr(service, "sql_filter_candidates", empty_candidates)

    response = await service.search(
        SearchRequest(query="cheap safe food", max_budget=50, min_safety=5)
    )
    assert response.candidate_count == 0
    assert response.results == []
    assert response.empty_reason in {
        "BUDGET_TOO_LOW",
        "SAFETY_TOO_STRICT",
        "NO_CANDIDATES",
    }
