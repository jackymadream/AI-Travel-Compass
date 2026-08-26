"""Meal schema + evaluator contract tests."""

from __future__ import annotations

import pytest

from src.schemas.itinerary import Activity, ActivityCategory
from src.services.agent_tools import evaluate_schedule_and_budget_tool


def test_activity_food_slot_fields() -> None:
    act = Activity(
        time_slot="12:00-13:30",
        poi_name="Japanese Ramen / Izakaya",
        category=ActivityCategory.FOOD,
        cost_usd=12,
        duration_minutes=90,
        description="Lunch food type",
        is_food_slot=True,
        meal_role="lunch",
    )
    assert act.is_food_slot is True
    assert act.meal_role == "lunch"
    assert act.is_custom is False


def test_missing_meals_violation() -> None:
    result = evaluate_schedule_and_budget_tool(
        daily_plan={
            "day_number": 1,
            "theme": "x",
            "activities": [
                {
                    "time_slot": "10:00-11:00",
                    "poi_name": "Park",
                    "category": "rest",
                    "cost_usd": 0,
                    "duration_minutes": 60,
                    "description": "rest",
                }
            ],
        },
        daily_budget_usd=100,
        pace="moderate",
    )
    assert result["is_valid"] is False
    assert any("MISSING_MEALS" in v for v in result["violations"])


@pytest.mark.asyncio
async def test_heuristic_plan_includes_lunch_dinner() -> None:
    from uuid import UUID

    from src.schemas.itinerary import ItineraryRequest, TripPace
    from src.services.agent_service import AgentService
    from src.services.agent_tools import MOCK_CITY_TOKYO

    service = AgentService(max_turns=3)
    result = await service.plan_itinerary(
        ItineraryRequest(
            city_id=UUID(MOCK_CITY_TOKYO),
            days=1,
            pace=TripPace.MODERATE,
            daily_budget_usd=120,
            preferences=["culture"],
        )
    )
    meals = [a for a in result.daily_plans[0].activities if a.is_food_slot]
    assert {m.meal_role for m in meals} >= {"lunch", "dinner"}
    for m in meals:
        # Food-type labels should not look like the mock restaurant brands.
        assert "Ichiran" not in m.poi_name
        assert "Ginza Sushi" not in m.poi_name
    lunch = next(a for a in result.daily_plans[0].activities if a.meal_role == "lunch")
    dinner = next(a for a in result.daily_plans[0].activities if a.meal_role == "dinner")
    assert lunch.poi_id
    assert dinner.poi_id
    # Meal stock photos disabled — UI uses lunch/dinner icons.
    assert lunch.photo_url in (None, "")
    assert dinner.photo_url in (None, "")
    afternoon = [
        a
        for a in result.daily_plans[0].activities
        if not a.is_food_slot and a.time_slot >= "12:00"
    ]
    for act in afternoon:
        assert act.time_slot >= "13:45"


def test_meal_pair_rotates_tokyo_and_osaka() -> None:
    from src.services.itinerary_i18n import meal_pair

    used: set[str] = set()
    tokyo: list[tuple[str, str]] = []
    for day in range(1, 4):
        pair = meal_pair("Tokyo", ["food"], day, "en", used=used)
        tokyo.append(pair)
        used.update(pair)
    lunches = [p[0] for p in tokyo]
    dinners = [p[1] for p in tokyo]
    assert len(set(lunches)) == 3
    assert len(set(dinners)) == 3
    assert len({*lunches, *dinners}) >= 5

    used = set()
    osaka: list[tuple[str, str]] = []
    for day in range(1, 4):
        pair = meal_pair("Osaka", ["food"], day, "zh-HK", used=used)
        osaka.append(pair)
        used.update(pair)
    assert len({p[0] for p in osaka}) == 3
    assert not all(p[0] == osaka[0][0] for p in osaka)


@pytest.mark.asyncio
async def test_heuristic_three_day_tokyo_varies_meals() -> None:
    from uuid import UUID

    from src.schemas.itinerary import ItineraryRequest, TripPace
    from src.services.agent_service import AgentService
    from src.services.agent_tools import MOCK_CITY_TOKYO

    service = AgentService(max_turns=3)
    result = await service.plan_itinerary(
        ItineraryRequest(
            city_id=UUID(MOCK_CITY_TOKYO),
            days=3,
            pace=TripPace.MODERATE,
            daily_budget_usd=150,
            preferences=["culture", "food"],
        )
    )
    lunches: list[str] = []
    dinners: list[str] = []
    labels: list[str] = []
    for day in result.daily_plans:
        for act in day.activities:
            if not act.is_food_slot:
                continue
            labels.append(act.poi_name)
            if act.meal_role == "lunch":
                lunches.append(act.poi_name)
            if act.meal_role == "dinner":
                dinners.append(act.poi_name)
    assert len(set(labels)) >= 5
    assert len(set(lunches)) >= 2
    assert not all(x == lunches[0] for x in lunches)


def test_meal_pair_skips_same_cuisine_family() -> None:
    from src.services.itinerary_i18n import cuisine_family, meal_pair

    lunch, dinner = meal_pair("Tokyo", ["food"], 2, "en")
    assert cuisine_family(lunch) != cuisine_family(dinner)
    sushi_lunch, sushi_dinner = meal_pair(
        "Tokyo", ["food"], 2, "en", used={"Japanese Ramen / Teishoku"}
    )
    # Day-2 rotation starts at sushi lunch; dinner must not also be sushi-family.
    assert "sushi" in sushi_lunch.lower() or "chirashi" in sushi_lunch.lower()
    assert cuisine_family(sushi_lunch) != cuisine_family(sushi_dinner)
    assert cuisine_family(sushi_dinner) != "sushi"


def test_meal_photo_disabled() -> None:
    from src.services.itinerary_i18n import meal_photo

    assert meal_photo("Kaiseki / Tofu Cuisine", "lunch") == ""
    assert meal_photo("Monjayaki / Okonomiyaki", "dinner") == ""
    assert meal_photo("Sushi Set", "dinner") == ""


def test_overlapping_lunch_and_rest_is_invalid() -> None:
    result = evaluate_schedule_and_budget_tool(
        daily_plan={
            "day_number": 1,
            "theme": "x",
            "activities": [
                {
                    "time_slot": "10:00-11:30",
                    "poi_name": "Temple",
                    "category": "attraction",
                    "cost_usd": 0,
                    "duration_minutes": 90,
                    "description": "visit",
                },
                {
                    "time_slot": "12:00-13:30",
                    "poi_name": "Japanese Ramen / Teishoku",
                    "category": "food",
                    "cost_usd": 12,
                    "duration_minutes": 90,
                    "description": "lunch",
                    "is_food_slot": True,
                    "meal_role": "lunch",
                },
                {
                    "time_slot": "12:00-13:00",
                    "poi_name": "Park rest",
                    "category": "rest",
                    "cost_usd": 0,
                    "duration_minutes": 60,
                    "description": "rest",
                },
                {
                    "time_slot": "18:30-20:00",
                    "poi_name": "Izakaya / Yakitori",
                    "category": "food",
                    "cost_usd": 20,
                    "duration_minutes": 90,
                    "description": "dinner",
                    "is_food_slot": True,
                    "meal_role": "dinner",
                },
            ],
        },
        daily_budget_usd=120,
        pace="moderate",
    )
    assert result["is_valid"] is False
    assert any("OVERLAPPING_SLOTS" in v for v in result["violations"])
