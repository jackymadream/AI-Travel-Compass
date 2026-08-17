"""
GET /api/v1/countries — TDD suite.

Red phase: these tests fail until schemas, router, and main app exist.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


SAMPLE_COUNTRIES: list[dict[str, Any]] = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "iso_code": "JP",
        "slug": "japan",
        "name": {"en": "Japan", "zh-HK": "日本", "ja": "日本"},
        "description": {
            "en": "Ancient tradition and modernity.",
            "zh-HK": "融合古老傳統與現代科技。",
            "ja": "伝統と最先端が融合する国。",
        },
        "safety_index": 5,
        "avg_daily_cost_usd": 120.0,
        "best_travel_season": {
            "seasons": ["spring", "autumn"],
            "months": [3, 4, 5, 10, 11],
            "label": {
                "en": "Spring & Autumn",
                "zh-HK": "春季與秋季",
                "ja": "春と秋",
            },
        },
        "region_tags": ["East Asia"],
        "tags": ["culture", "food", "urban"],
        "photo_url": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1600",
        "top_cities": [
            {
                "slug": "tokyo",
                "name": {"en": "Tokyo", "zh-HK": "東京", "ja": "東京"},
                "photo_url": None,
            },
            {
                "slug": "kyoto",
                "name": {"en": "Kyoto", "zh-HK": "京都", "ja": "京都"},
                "photo_url": None,
            },
        ],
        "is_active": True,
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "iso_code": "VN",
        "slug": "vietnam",
        "name": {"en": "Vietnam", "zh-HK": "越南", "ja": "ベトナム"},
        "description": {
            "en": "Street food and karsts.",
            "zh-HK": "街頭美食與峰林。",
            "ja": "屋台グルメとカルスト。",
        },
        "safety_index": 3,
        "avg_daily_cost_usd": 40.0,
        "best_travel_season": {
            "seasons": ["spring", "autumn"],
            "months": [3, 4, 10, 11],
            "label": {
                "en": "Spring & Autumn",
                "zh-HK": "春季與秋季",
                "ja": "春と秋",
            },
        },
        "region_tags": ["Southeast Asia"],
        "tags": ["food", "budget", "nature"],
        "photo_url": "https://images.unsplash.com/photo-1528127269322-539801943592?w=1600",
        "top_cities": [
            {
                "slug": "hanoi",
                "name": {"en": "Hanoi", "zh-HK": "河內", "ja": "ハノイ"},
                "photo_url": None,
            },
            {
                "slug": "da-nang",
                "name": {"en": "Da Nang", "zh-HK": "峴港", "ja": "ダナン"},
                "photo_url": None,
            },
        ],
        "is_active": True,
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "iso_code": "IS",
        "slug": "iceland",
        "name": {"en": "Iceland", "zh-HK": "冰島", "ja": "アイスランド"},
        "description": {
            "en": "Volcanoes and northern lights.",
            "zh-HK": "火山與北極光。",
            "ja": "火山とオーロラ。",
        },
        "safety_index": 5,
        "avg_daily_cost_usd": 180.0,
        "best_travel_season": {
            "seasons": ["summer"],
            "months": [6, 7, 8],
            "label": {
                "en": "Midnight sun summer",
                "zh-HK": "午夜太陽夏季",
                "ja": "白夜の夏",
            },
        },
        "region_tags": ["Northern Europe"],
        "tags": ["nature", "adventure", "scenic"],
        "photo_url": "https://images.unsplash.com/photo-1504829857797-ddff29ac9f1b?w=1600",
        "top_cities": [
            {
                "slug": "reykjavik",
                "name": {"en": "Reykjavik", "zh-HK": "雷克雅未克", "ja": "レイキャビク"},
                "photo_url": None,
            },
            {
                "slug": "vik",
                "name": {"en": "Vik", "zh-HK": "維克", "ja": "ヴィーク"},
                "photo_url": None,
            },
        ],
        "is_active": True,
    },
]


def _mock_supabase(rows: list[dict[str, Any]]) -> MagicMock:
    """Supabase query chain that returns filtered rows based on applied filters."""
    client = MagicMock()

    state: dict[str, Any] = {
        "max_budget": None,
        "min_safety": None,
        "tags": None,
    }

    def execute() -> MagicMock:
        result = MagicMock()
        filtered = [r for r in rows if r.get("is_active", True)]
        if state["max_budget"] is not None:
            filtered = [
                r for r in filtered if r["avg_daily_cost_usd"] <= state["max_budget"]
            ]
        if state["min_safety"] is not None:
            filtered = [
                r for r in filtered if r["safety_index"] >= state["min_safety"]
            ]
        if state["tags"]:
            wanted = set(state["tags"])
            filtered = [
                r
                for r in filtered
                if wanted.intersection({t.lower() for t in (r.get("tags") or [])})
            ]
        result.data = filtered
        return result

    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query

    def lte(column: str, value: Any) -> MagicMock:
        if column == "avg_daily_cost_usd":
            state["max_budget"] = float(value)
        return query

    def gte(column: str, value: Any) -> MagicMock:
        if column == "safety_index":
            state["min_safety"] = int(value)
        return query

    def overlaps(column: str, value: Any) -> MagicMock:
        if column == "tags":
            state["tags"] = [str(v).lower() for v in value]
        return query

    query.lte.side_effect = lte
    query.gte.side_effect = gte
    query.overlaps.side_effect = overlaps
    query.execute.side_effect = execute
    client.table.return_value = query
    return client


@pytest.fixture
def client() -> TestClient:
    from src.deps import get_supabase
    from src.main import app

    mock = _mock_supabase(SAMPLE_COUNTRIES)
    app.dependency_overrides[get_supabase] = lambda: mock
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestListCountriesMultilingual:
    def test_default_locale_is_english(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 3
        japan = next(c for c in body if c["iso_code"] == "JP")
        assert japan["name"] == "Japan"
        assert japan["description"] == "Ancient tradition and modernity."

    def test_locale_en(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries", params={"locale": "en"})
        assert response.status_code == 200
        japan = next(c for c in response.json() if c["iso_code"] == "JP")
        assert japan["name"] == "Japan"
        assert "tradition" in japan["description"].lower()

    def test_locale_zh_hk_traditional_chinese(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries", params={"locale": "zh-HK"})
        assert response.status_code == 200
        japan = next(c for c in response.json() if c["iso_code"] == "JP")
        assert japan["name"] == "日本"
        assert japan["description"] == "融合古老傳統與現代科技。"

    def test_locale_ja(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries", params={"locale": "ja"})
        assert response.status_code == 200
        japan = next(c for c in response.json() if c["iso_code"] == "JP")
        assert japan["name"] == "日本"
        assert "伝統" in japan["description"]

    def test_invalid_locale_rejected(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries", params={"locale": "fr"})
        assert response.status_code == 422


class TestListCountriesDeterministicFiltering:
    def test_filter_by_max_budget(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/countries",
            params={"max_budget": 100},
        )
        assert response.status_code == 200
        body = response.json()
        iso_codes = {c["iso_code"] for c in body}
        assert iso_codes == {"VN"}
        assert all(c["avg_daily_cost_usd"] <= 100 for c in body)

    def test_filter_by_min_safety_rating(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/countries",
            params={"min_safety_rating": 5},
        )
        assert response.status_code == 200
        body = response.json()
        iso_codes = {c["iso_code"] for c in body}
        assert iso_codes == {"JP", "IS"}
        assert all(c["safety_index"] >= 5 for c in body)

    def test_filter_max_budget_and_min_safety_combined(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/countries",
            params={"max_budget": 150, "min_safety_rating": 5},
        )
        assert response.status_code == 200
        body = response.json()
        iso_codes = {c["iso_code"] for c in body}
        assert iso_codes == {"JP"}
        assert all(
            c["avg_daily_cost_usd"] <= 150 and c["safety_index"] >= 5 for c in body
        )

    def test_filter_by_tags_overlap(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/countries",
            params=[("tags", "nature"), ("tags", "adventure")],
        )
        assert response.status_code == 200
        body = response.json()
        iso_codes = {c["iso_code"] for c in body}
        assert iso_codes == {"VN", "IS"}

    def test_filter_by_comma_separated_tags(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/countries",
            params={"tags": "culture,urban"},
        )
        assert response.status_code == 200
        body = response.json()
        assert {c["iso_code"] for c in body} == {"JP"}

    def test_response_includes_deterministic_fields(self, client: TestClient) -> None:
        response = client.get("/api/v1/countries", params={"locale": "en"})
        assert response.status_code == 200
        country = next(c for c in response.json() if c["iso_code"] == "JP")
        assert "id" in country
        assert country["slug"] == "japan"
        assert "iso_code" in country
        assert "name" in country
        assert "description" in country
        assert "safety_index" in country
        assert "avg_daily_cost_usd" in country
        assert "best_travel_season" in country
        assert country["best_season"] == "Spring & Autumn"
        assert "region_tags" in country
        assert country["tags"] == ["culture", "food", "urban"]
        assert "unsplash.com" in (country["photo_url"] or "")
        assert len(country["top_cities"]) == 2
        assert country["top_cities"][0]["name"] == "Tokyo"
