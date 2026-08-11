"""Unit tests for Phase 3 agent tools (POI search + schedule/budget evaluator)."""

from __future__ import annotations

import pytest

from src.services.agent_tools import (
    MOCK_CITY_TOKYO,
    evaluate_schedule_and_budget_tool,
    search_pois_tool,
)


def test_search_pois_filters_by_city_and_category() -> None:
    pois = search_pois_tool(
        city_id=MOCK_CITY_TOKYO,
        category="food",
        preferences=[],
        limit=10,
    )

    assert pois
    assert all(p["category"] == "food" for p in pois)
    assert all(p["city_id"] == MOCK_CITY_TOKYO for p in pois)
    for p in pois:
        assert {"name", "category", "cost_usd", "duration_minutes", "description"} <= set(
            p
        )


def test_search_pois_prefers_matching_preferences_and_respects_limit() -> None:
    pois = search_pois_tool(
        city_id=MOCK_CITY_TOKYO,
        category="attraction",
        preferences=["museum", "culture"],
        limit=2,
    )

    assert len(pois) == 2
    # Preference-aligned POIs should rank first.
    top_tags = " ".join(pois[0].get("tags", []) + [pois[0]["name"], pois[0]["description"]]).lower()
    assert "museum" in top_tags or "culture" in top_tags


def test_search_pois_unknown_city_returns_empty() -> None:
    assert (
        search_pois_tool(
            city_id="00000000-0000-0000-0000-000000000000",
            category="attraction",
            preferences=[],
        )
        == []
    )


def _sample_day(*, activities: list[dict]) -> dict:
    return {
        "day_number": 1,
        "theme": "City highlights",
        "activities": activities,
    }


def test_evaluate_schedule_valid_moderate_plan() -> None:
    daily_plan = _sample_day(
        activities=[
            {
                "time_slot": "09:00-11:00",
                "poi_name": "Senso-ji",
                "category": "attraction",
                "cost_usd": 5,
                "duration_minutes": 120,
                "description": "Temple visit",
            },
            {
                "time_slot": "12:00-13:00",
                "poi_name": "Ramen shop",
                "category": "food",
                "cost_usd": 15,
                "duration_minutes": 60,
                "description": "Lunch",
            },
            {
                "time_slot": "14:00-15:00",
                "poi_name": "Park rest",
                "category": "rest",
                "cost_usd": 0,
                "duration_minutes": 60,
                "description": "Break",
            },
        ]
    )

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=100.0,
        pace="moderate",
    )

    assert result["is_valid"] is True
    assert result["violations"] == []
    assert result["total_cost_usd"] == pytest.approx(20.0)
    # 120+60+60 activity + travel buffer between hops
    assert result["total_duration_minutes"] > 240
    assert "suggested_adjustments" in result


def test_evaluate_schedule_over_budget_reports_shortfall() -> None:
    daily_plan = _sample_day(
        activities=[
            {
                "time_slot": "10:00-12:00",
                "poi_name": "Fine dining",
                "category": "food",
                "cost_usd": 80,
                "duration_minutes": 120,
                "description": "Kaiseki",
            },
            {
                "time_slot": "14:00-16:00",
                "poi_name": "Museum",
                "category": "attraction",
                "cost_usd": 40,
                "duration_minutes": 120,
                "description": "Art",
            },
        ]
    )

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=100.0,
        pace="moderate",
    )

    assert result["is_valid"] is False
    assert result["total_cost_usd"] == pytest.approx(120.0)
    assert any("Over budget by $20" in v for v in result["violations"])
    assert result["suggested_adjustments"]


def test_evaluate_schedule_too_packed_for_relaxed_pace() -> None:
    activities = [
        {
            "time_slot": f"{9 + i}:00-{10 + i}:00",
            "poi_name": f"Stop {i}",
            "category": "attraction" if i % 2 == 0 else "food",
            "cost_usd": 10,
            "duration_minutes": 90,
            "description": f"Activity {i}",
        }
        for i in range(5)
    ]
    daily_plan = _sample_day(activities=activities)

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=200.0,
        pace="relaxed",
    )

    assert result["is_valid"] is False
    assert any("relaxed" in v.lower() for v in result["violations"])
    assert any("packed" in v.lower() or "too" in v.lower() for v in result["violations"])
