"""
POST /api/v1/search — TDD suite for hybrid RAG search endpoint.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.schemas.country import Locale
from src.schemas.search import SearchHit, SearchRequest, SearchResponse

CITY_ID = UUID("11111111-1111-1111-1111-111111111111")
COUNTRY_ID = UUID("22222222-2222-2222-2222-222222222222")

LOCALIZED: dict[str, dict[str, str]] = {
    "en": {"name": "Tokyo", "description": "Neon capital with great food."},
    "zh-HK": {"name": "東京", "description": "霓虹首都，美食豐富。"},
    "ja": {"name": "東京", "description": "ネオンの首都、食が充実。"},
}


def _hit_for_locale(locale: Locale, *, score: float = 0.91) -> SearchHit:
    copy = LOCALIZED[locale.value]
    return SearchHit(
        city_id=CITY_ID,
        country_id=COUNTRY_ID,
        iso_code="JP",
        name=copy["name"],
        description=copy["description"],
        safety_index=5,
        avg_daily_cost_usd=130.0,
        tags=["food"],
        score=score,
        vector_score=0.9,
    )


def _mock_search_service() -> MagicMock:
    service = MagicMock()

    async def search(request: SearchRequest) -> SearchResponse:
        if request.max_budget is not None and request.max_budget < 10:
            return SearchResponse(
                query=request.query,
                locale=request.locale,
                intent=None,
                candidate_count=0,
                empty_reason="BUDGET_TOO_LOW",
                results=[],
            )

        return SearchResponse(
            query=request.query,
            locale=request.locale,
            intent=None,
            candidate_count=1,
            empty_reason=None,
            results=[_hit_for_locale(request.locale)],
        )

    service.search = AsyncMock(side_effect=search)
    return service


@pytest.fixture
def client() -> TestClient:
    from src.main import app
    from src.routers.search import get_search_service

    mock = _mock_search_service()
    app.dependency_overrides[get_search_service] = lambda: mock
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestPostSearchHappyPath:
    def test_natural_language_query_with_hard_filters_returns_200(
        self, client: TestClient
    ) -> None:
        payload: dict[str, Any] = {
            "query": "quiet food city by the sea",
            "locale": "en",
            "max_budget": 150,
            "min_safety": 4,
            "tags": ["food"],
            "limit": 5,
        }
        response = client.post("/api/v1/search", json=payload)
        assert response.status_code == 200

        body = response.json()
        assert body["query"] == payload["query"]
        assert body["locale"] == "en"
        assert body["candidate_count"] >= 1
        assert body["empty_reason"] is None
        assert isinstance(body["results"], list)
        assert len(body["results"]) >= 1

        hit = body["results"][0]
        assert hit["name"]
        assert hit["description"]
        assert hit["safety_index"] >= payload["min_safety"]
        assert hit["avg_daily_cost_usd"] <= payload["max_budget"]
        assert "score" in hit
        assert hit["score"] > 0


class TestPostSearchEmptyResults:
    def test_unrealistically_low_budget_returns_empty_response(
        self, client: TestClient
    ) -> None:
        payload = {
            "query": "luxury safari",
            "locale": "en",
            "max_budget": 1,
            "min_safety": 5,
        }
        response = client.post("/api/v1/search", json=payload)
        assert response.status_code == 200

        body = response.json()
        assert body["results"] == []
        assert body["candidate_count"] == 0
        assert body["empty_reason"] == "BUDGET_TOO_LOW"


class TestPostSearchMultilingual:
    @pytest.mark.parametrize(
        ("locale", "expected_name", "expected_snippet"),
        [
            ("en", "Tokyo", "Neon"),
            ("zh-HK", "東京", "霓虹"),
            ("ja", "東京", "ネオン"),
        ],
    )
    def test_response_uses_requested_locale(
        self,
        client: TestClient,
        locale: str,
        expected_name: str,
        expected_snippet: str,
    ) -> None:
        payload = {
            "query": "food culture city",
            "locale": locale,
            "max_budget": 200,
            "min_safety": 3,
            "tags": ["food"],
        }
        response = client.post("/api/v1/search", json=payload)
        assert response.status_code == 200

        body = response.json()
        assert body["locale"] == locale
        assert len(body["results"]) >= 1
        hit = body["results"][0]
        assert hit["name"] == expected_name
        assert expected_snippet in hit["description"]
