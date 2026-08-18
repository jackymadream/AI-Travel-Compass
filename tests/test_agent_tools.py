"""Unit tests for Phase 3 agent tools (POI search + schedule/budget evaluator)."""

from __future__ import annotations

import pytest

from src.services.agent_tools import (
    MOCK_CITY_TOKYO,
    evaluate_schedule_and_budget_tool,
    pace_constraint_prompt,
    pace_only_violations,
    scheduled_total_minutes,
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


def _meal(role: str, *, cost: float = 15.0) -> dict:
    return {
        "time_slot": "12:00-13:30" if role == "lunch" else "18:30-20:00",
        "poi_name": "Regional Lunch" if role == "lunch" else "Local Dinner",
        "category": "food",
        "cost_usd": cost,
        "duration_minutes": 90,
        "description": f"{role} food type",
        "is_food_slot": True,
        "meal_role": role,
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
            _meal("lunch", cost=15),
            {
                "time_slot": "14:00-15:00",
                "poi_name": "Park rest",
                "category": "rest",
                "cost_usd": 0,
                "duration_minutes": 60,
                "description": "Break",
            },
            _meal("dinner", cost=20),
        ]
    )

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=100.0,
        pace="moderate",
    )

    assert result["is_valid"] is True
    assert result["violations"] == []
    assert result["total_cost_usd"] == pytest.approx(40.0)
    assert result["total_duration_minutes"] > 240
    assert "suggested_adjustments" in result


def test_evaluate_schedule_missing_meals() -> None:
    daily_plan = _sample_day(
        activities=[
            {
                "time_slot": "10:00-12:00",
                "poi_name": "Museum",
                "category": "attraction",
                "cost_usd": 10,
                "duration_minutes": 120,
                "description": "Art",
            }
        ]
    )
    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=100.0,
        pace="moderate",
    )
    assert result["is_valid"] is False
    assert any("MISSING_MEALS" in v for v in result["violations"])


def test_evaluate_schedule_over_budget_reports_shortfall() -> None:
    daily_plan = _sample_day(
        activities=[
            {
                "time_slot": "10:00-12:00",
                "poi_name": "Fine dining venue",
                "category": "attraction",
                "cost_usd": 80,
                "duration_minutes": 120,
                "description": "Kaiseki",
            },
            _meal("lunch", cost=20),
            {
                "time_slot": "14:00-16:00",
                "poi_name": "Museum",
                "category": "attraction",
                "cost_usd": 40,
                "duration_minutes": 120,
                "description": "Art",
            },
            _meal("dinner", cost=20),
        ]
    )

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=100.0,
        pace="moderate",
    )

    assert result["is_valid"] is False
    assert result["total_cost_usd"] == pytest.approx(160.0)
    assert any("Over budget" in v for v in result["violations"])
    assert result["suggested_adjustments"]


def test_evaluate_schedule_too_packed_for_relaxed_pace() -> None:
    activities = [
        {
            "time_slot": f"{9 + i}:00-{10 + i}:00",
            "poi_name": f"Stop {i}",
            "category": "attraction",
            "cost_usd": 10,
            "duration_minutes": 90,
            "description": f"Activity {i}",
            "is_food_slot": False,
        }
        for i in range(4)
    ]
    activities.extend([_meal("lunch"), _meal("dinner")])
    daily_plan = _sample_day(activities=activities)

    result = evaluate_schedule_and_budget_tool(
        daily_plan=daily_plan,
        daily_budget_usd=200.0,
        pace="relaxed",
    )

    assert result["is_valid"] is False
    assert any("relaxed" in v.lower() for v in result["violations"])
    assert any("packed" in v.lower() or "too" in v.lower() for v in result["violations"])
    assert any("30 min" in s or "travel" in s.lower() for s in result["suggested_adjustments"])


def test_scheduled_total_minutes_includes_travel_hops() -> None:
    activities = [
        {"duration_minutes": 90},
        {"duration_minutes": 60},
        {"duration_minutes": 90},
    ]
    # 240 activity + 2 hops × 30 travel
    assert scheduled_total_minutes(activities) == 300


def test_pace_only_violations_ignores_budget_and_meals() -> None:
    packed = ["Schedule too packed for moderate pace (690 minutes including travel; max 600)"]
    assert pace_only_violations(packed) is True
    assert pace_only_violations(["Over budget by $999"]) is False
    assert pace_only_violations(["MISSING_MEALS: need Lunch and Dinner food slots"]) is False
    assert pace_only_violations(packed + ["Over budget by $10"]) is False


def test_pace_constraint_prompt_includes_caps_and_travel_buffer() -> None:
    text = pace_constraint_prompt("moderate")
    assert "7" in text
    assert "600" in text
    assert "30" in text

