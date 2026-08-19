"""
Phase 3 agent loop + POST /api/v1/itineraries/generate tests.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.schemas.itinerary import ItineraryRequest, TripPace
from src.services.agent_service import AgentPlanningError, AgentService
from src.services.agent_tools import MOCK_CITY_TOKYO

TOKYO = UUID(MOCK_CITY_TOKYO)


@pytest.mark.asyncio
async def test_plan_itinerary_multi_day_grounded_and_under_budget() -> None:
    service = AgentService(max_turns=3)
    request = ItineraryRequest(
        city_id=TOKYO,
        days=3,
        pace=TripPace.MODERATE,
        daily_budget_usd=100.0,
        preferences=["food", "museum"],
        locale="en",
    )

    result = await service.plan_itinerary(request)

    assert result.city_name == "Tokyo"
    assert len(result.daily_plans) == 3
    assert [d.day_number for d in result.daily_plans] == [1, 2, 3]
    assert result.total_cost_usd == pytest.approx(
        sum(d.estimated_daily_cost for d in result.daily_plans)
    )
    assert result.agent_reasoning
    assert result.user_summary
    assert result.prep_tips

    for day in result.daily_plans:
        assert day.estimated_daily_cost <= request.daily_budget_usd
        assert day.activities
        meals = [a for a in day.activities if a.is_food_slot]
        assert len(meals) >= 2
        assert {m.meal_role for m in meals} >= {"lunch", "dinner"}
        for act in day.activities:
            assert act.poi_name
            assert act.category.value in {"attraction", "food", "rest"}
            assert act.cost_usd >= 0
            assert act.duration_minutes >= 1

    non_meal = [
        a.poi_name
        for d in result.daily_plans
        for a in d.activities
        if not a.is_food_slot
    ]
    assert len(non_meal) == len(set(non_meal))


@pytest.mark.asyncio
async def test_plan_itinerary_relaxed_pace_limits_activity_count() -> None:
    service = AgentService(max_turns=3)
    request = ItineraryRequest(
        city_id=TOKYO,
        days=1,
        pace=TripPace.RELAXED,
        daily_budget_usd=150.0,
        preferences=["culture"],
    )

    result = await service.plan_itinerary(request)
    assert len(result.daily_plans) == 1
    assert len(result.daily_plans[0].activities) <= 5
    meals = [a for a in result.daily_plans[0].activities if a.is_food_slot]
    assert len(meals) >= 2
    assert {m.meal_role for m in meals} >= {"lunch", "dinner"}


@pytest.mark.asyncio
async def test_plan_itinerary_retries_when_draft_over_budget() -> None:
    """Inject an LLM that first proposes an over-budget day; loop must refine."""

    class OverBudgetThenOkLLM:
        def __init__(self) -> None:
            self.calls = 0

        def propose_daily_plan(
            self,
            *,
            request: ItineraryRequest,
            day_number: int,
            poi_pool: list[dict[str, Any]],
            previous_violations: list[str],
            turn: int,
        ) -> dict[str, Any]:
            self.calls += 1
            expensive = next(p for p in poi_pool if p["name"] == "Ginza Sushi Counter")
            museum = next(p for p in poi_pool if p["name"] == "Tokyo National Museum")
            rest = next(p for p in poi_pool if p["category"] == "rest")
            # Always return costly trio + required meals; refine should drop venue cost.
            return {
                "day_number": day_number,
                "theme": "Luxury day",
                "activities": [
                    {
                        "time_slot": "10:00-11:30",
                        "poi_name": expensive["name"],
                        "category": expensive["category"],
                        "cost_usd": expensive["cost_usd"],
                        "duration_minutes": expensive["duration_minutes"],
                        "description": expensive["description"],
                        "is_food_slot": False,
                    },
                    {
                        "time_slot": "12:00-13:30",
                        "poi_name": "Japanese Ramen / Teishoku",
                        "category": "food",
                        "cost_usd": 12,
                        "duration_minutes": 90,
                        "description": "Lunch food type",
                        "is_food_slot": True,
                        "meal_role": "lunch",
                    },
                    {
                        "time_slot": "14:00-16:30",
                        "poi_name": museum["name"],
                        "category": museum["category"],
                        "cost_usd": museum["cost_usd"],
                        "duration_minutes": museum["duration_minutes"],
                        "description": museum["description"],
                        "is_food_slot": False,
                    },
                    {
                        "time_slot": "16:45-17:45",
                        "poi_name": rest["name"],
                        "category": rest["category"],
                        "cost_usd": rest["cost_usd"],
                        "duration_minutes": rest["duration_minutes"],
                        "description": rest["description"],
                        "is_food_slot": False,
                    },
                    {
                        "time_slot": "18:30-20:00",
                        "poi_name": "Izakaya / Sushi Set",
                        "category": "food",
                        "cost_usd": 20,
                        "duration_minutes": 90,
                        "description": "Dinner food type",
                        "is_food_slot": True,
                        "meal_role": "dinner",
                    },
                ],
            }

    llm = OverBudgetThenOkLLM()
    service = AgentService(max_turns=3, llm_client=llm)
    request = ItineraryRequest(
        city_id=TOKYO,
        days=1,
        pace=TripPace.MODERATE,
        daily_budget_usd=80.0,
        preferences=["food"],
    )

    result = await service.plan_itinerary(request)

    assert result.daily_plans[0].estimated_daily_cost <= 80.0
    assert llm.calls >= 1


@pytest.mark.asyncio
async def test_plan_itinerary_unknown_city_raises() -> None:
    service = AgentService()
    request = ItineraryRequest(
        city_id=UUID("00000000-0000-0000-0000-000000000000"),
        days=1,
        pace=TripPace.MODERATE,
        daily_budget_usd=80.0,
    )
    with pytest.raises(AgentPlanningError, match="No POIs"):
        await service.plan_itinerary(request)


@pytest.mark.asyncio
async def test_max_turns_exhausted_raises_planning_error() -> None:
    def always_bad_evaluate(
        daily_plan: dict,
        daily_budget_usd: float,
        pace: str,
    ) -> dict:
        return {
            "is_valid": False,
            "violations": ["Over budget by $999"],
            "suggested_adjustments": ["Impossible"],
            "total_cost_usd": 999.0,
            "total_duration_minutes": 10,
            "activity_minutes": 10,
            "travel_buffer_minutes": 0,
        }

    service = AgentService(max_turns=3, evaluate_schedule=always_bad_evaluate)
    request = ItineraryRequest(
        city_id=TOKYO,
        days=1,
        pace=TripPace.MODERATE,
        daily_budget_usd=100.0,
    )
    with pytest.raises(AgentPlanningError, match="within 3 turns"):
        await service.plan_itinerary(request)


@pytest.mark.asyncio
async def test_max_turns_pace_only_returns_best_effort_with_warning() -> None:
    def always_packed(
        daily_plan: dict,
        daily_budget_usd: float,
        pace: str,
    ) -> dict:
        return {
            "is_valid": False,
            "violations": [
                "Schedule too packed for moderate pace "
                "(690 minutes including travel; max 600)"
            ],
            "suggested_adjustments": ["Drop attractions until under 600 minutes."],
            "total_cost_usd": 40.0,
            "total_duration_minutes": 690,
            "activity_minutes": 540,
            "travel_buffer_minutes": 150,
        }

    service = AgentService(max_turns=3, evaluate_schedule=always_packed)
    request = ItineraryRequest(
        city_id=TOKYO,
        days=1,
        pace=TripPace.MODERATE,
        daily_budget_usd=100.0,
    )
    result = await service.plan_itinerary(request)
    assert result.daily_plans
    assert result.daily_plans[0].activities
    assert result.daily_plans[0].warnings
    assert any("packed" in w.lower() for w in result.daily_plans[0].warnings)


def test_refine_drops_attractions_until_under_moderate_duration() -> None:
    service = AgentService(max_turns=3)
    activities = [
        {
            "time_slot": "09:00-11:30",
            "poi_name": "Stop 0",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 150,
            "description": "long stop",
            "is_food_slot": False,
        },
        {
            "time_slot": "11:45-13:15",
            "poi_name": "Regional Lunch",
            "category": "food",
            "cost_usd": 15,
            "duration_minutes": 90,
            "description": "lunch",
            "is_food_slot": True,
            "meal_role": "lunch",
        },
        {
            "time_slot": "13:30-16:00",
            "poi_name": "Stop 1",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 150,
            "description": "long stop",
            "is_food_slot": False,
        },
        {
            "time_slot": "16:15-18:45",
            "poi_name": "Stop 2",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 150,
            "description": "long stop",
            "is_food_slot": False,
        },
        {
            "time_slot": "19:00-21:30",
            "poi_name": "Stop 3",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 150,
            "description": "long stop",
            "is_food_slot": False,
        },
        {
            "time_slot": "21:45-23:15",
            "poi_name": "Local Dinner",
            "category": "food",
            "cost_usd": 20,
            "duration_minutes": 90,
            "description": "dinner",
            "is_food_slot": True,
            "meal_role": "dinner",
        },
    ]
    draft = {"day_number": 1, "theme": "Packed", "activities": activities}
    refined = service._refine_draft_after_violation(
        draft,
        [
            "Schedule too packed for moderate pace "
            "(900 minutes including travel; max 600)"
        ],
        pace="moderate",
    )
    from src.services.agent_tools import evaluate_schedule_and_budget_tool

    result = evaluate_schedule_and_budget_tool(
        daily_plan=refined,
        daily_budget_usd=200.0,
        pace="moderate",
    )
    assert result["is_valid"] is True
    meals = [a for a in refined["activities"] if a.get("is_food_slot")]
    assert len(meals) == 2


def _activity(
    *,
    time_slot: str,
    poi_name: str,
    category: str = "attraction",
    duration_minutes: int = 90,
    cost_usd: float = 0,
    is_food_slot: bool = False,
    meal_role: str | None = None,
) -> dict:
    return {
        "time_slot": time_slot,
        "poi_name": poi_name,
        "category": category,
        "cost_usd": cost_usd,
        "duration_minutes": duration_minutes,
        "description": poi_name,
        "is_food_slot": is_food_slot,
        "meal_role": meal_role,
    }


def test_refine_separates_sushi_chirashi_lunch_from_shrine() -> None:
    """Gemini left lunch overlapping Karasumori Shrine; refine must unstick slots."""
    from src.services.agent_tools import evaluate_schedule_and_budget_tool
    from src.services.itinerary_eval import overlapping_activity_pairs

    service = AgentService(max_turns=3)
    draft = {
        "day_number": 2,
        "theme": "Day 2",
        "activities": [
            _activity(
                time_slot="09:00-11:00",
                poi_name="Senso-ji Temple",
                duration_minutes=120,
            ),
            _activity(
                time_slot="12:00-14:00",
                poi_name="Sushi / Chirashi",
                category="food",
                duration_minutes=90,
                cost_usd=12,
                is_food_slot=True,
                meal_role="lunch",
            ),
            _activity(
                time_slot="13:00-14:30",
                poi_name="Karasumori Shrine",
                duration_minutes=90,
            ),
            _activity(
                time_slot="18:30-20:00",
                poi_name="Yakiniku / Shabu-shabu",
                category="food",
                duration_minutes=90,
                cost_usd=20,
                is_food_slot=True,
                meal_role="dinner",
            ),
        ],
    }
    assert overlapping_activity_pairs(draft["activities"])

    refined = service._refine_draft_after_violation(
        draft,
        ["OVERLAPPING_SLOTS: Sushi / Chirashi / Karasumori Shrine"],
        pace="moderate",
    )
    result = evaluate_schedule_and_budget_tool(
        daily_plan=refined,
        daily_budget_usd=200.0,
        pace="moderate",
    )
    assert overlapping_activity_pairs(refined["activities"]) == []
    assert result["is_valid"] is True
    names = {a["poi_name"] for a in refined["activities"]}
    assert "Sushi / Chirashi" in names
    assert "Karasumori Shrine" in names


def test_refine_moves_morning_shrine_that_runs_into_lunch() -> None:
    from src.services.agent_tools import evaluate_schedule_and_budget_tool
    from src.services.itinerary_eval import overlapping_activity_pairs

    service = AgentService(max_turns=3)
    draft = {
        "day_number": 2,
        "theme": "Day 2",
        "activities": [
            _activity(
                time_slot="11:00-13:00",
                poi_name="Karasumori Shrine",
                duration_minutes=120,
            ),
            _activity(
                time_slot="12:00-13:30",
                poi_name="Sushi / Chirashi",
                category="food",
                duration_minutes=90,
                cost_usd=12,
                is_food_slot=True,
                meal_role="lunch",
            ),
            _activity(
                time_slot="18:30-20:00",
                poi_name="Yakiniku / Shabu-shabu",
                category="food",
                duration_minutes=90,
                cost_usd=20,
                is_food_slot=True,
                meal_role="dinner",
            ),
        ],
    }
    refined = service._refine_draft_after_violation(
        draft,
        ["OVERLAPPING_SLOTS: Sushi / Chirashi / Karasumori Shrine"],
        pace="moderate",
    )
    assert overlapping_activity_pairs(refined["activities"]) == []
    result = evaluate_schedule_and_budget_tool(
        daily_plan=refined,
        daily_budget_usd=200.0,
        pace="moderate",
    )
    assert result["is_valid"] is True


@pytest.mark.asyncio
async def test_plan_itinerary_resolves_persistent_lunch_shrine_overlap() -> None:
    class OverlappingLunchLLM:
        def propose_daily_plan(
            self,
            *,
            request: ItineraryRequest,
            day_number: int,
            poi_pool: list[dict[str, Any]],
            previous_violations: list[str],
            turn: int,
        ) -> dict[str, Any]:
            shrine = next(
                (p for p in poi_pool if "shrine" in str(p.get("name") or "").lower()),
                next(p for p in poi_pool if p.get("category") == "attraction"),
            )
            return {
                "day_number": day_number,
                "theme": "Overlap day",
                "activities": [
                    {
                        "time_slot": "12:00-14:00",
                        "poi_name": "Sushi / Chirashi",
                        "category": "food",
                        "cost_usd": 12,
                        "duration_minutes": 90,
                        "description": "lunch",
                        "is_food_slot": True,
                        "meal_role": "lunch",
                    },
                    {
                        "time_slot": "13:00-14:30",
                        "poi_name": shrine["name"],
                        "category": shrine["category"],
                        "cost_usd": shrine["cost_usd"],
                        "duration_minutes": shrine["duration_minutes"],
                        "description": shrine["description"],
                        "is_food_slot": False,
                    },
                    {
                        "time_slot": "18:30-20:00",
                        "poi_name": "Yakiniku / Shabu-shabu",
                        "category": "food",
                        "cost_usd": 20,
                        "duration_minutes": 90,
                        "description": "dinner",
                        "is_food_slot": True,
                        "meal_role": "dinner",
                    },
                ],
            }

    service = AgentService(max_turns=3, llm_client=OverlappingLunchLLM())
    request = ItineraryRequest(
        city_id=TOKYO,
        days=1,
        pace=TripPace.MODERATE,
        daily_budget_usd=120.0,
    )
    result = await service.plan_itinerary(request)
    assert result.daily_plans
    assert result.daily_plans[0].activities
    from src.services.itinerary_eval import overlapping_activity_pairs

    acts = [a.model_dump() for a in result.daily_plans[0].activities]
    assert overlapping_activity_pairs(acts) == []



@pytest.fixture
def client() -> TestClient:
    from src.main import app
    from src.routers.itinerary import get_agent_service

    app.dependency_overrides[get_agent_service] = lambda: AgentService(max_turns=3)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestPostGenerateItinerary:
    def test_generate_returns_structured_multi_day_plan(
        self, client: TestClient
    ) -> None:
        payload = {
            "city_id": MOCK_CITY_TOKYO,
            "days": 2,
            "pace": "moderate",
            "daily_budget_usd": 100,
            "preferences": ["food"],
            "locale": "en",
        }
        response = client.post("/api/v1/itineraries/generate", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["city_name"] == "Tokyo"
        assert len(body["daily_plans"]) == 2
        assert body["total_cost_usd"] >= 0
        assert body["agent_reasoning"]
        for day in body["daily_plans"]:
            assert day["estimated_daily_cost"] <= 100
            assert day["activities"]

    def test_generate_rejects_invalid_days(self, client: TestClient) -> None:
        payload = {
            "city_id": MOCK_CITY_TOKYO,
            "days": 9,
            "pace": "moderate",
            "daily_budget_usd": 100,
        }
        response = client.post("/api/v1/itineraries/generate", json=payload)
        assert response.status_code == 422

    def test_generate_unknown_city_returns_422(self, client: TestClient) -> None:
        payload = {
            "city_id": "00000000-0000-0000-0000-000000000000",
            "days": 1,
            "pace": "relaxed",
            "daily_budget_usd": 80,
        }
        response = client.post("/api/v1/itineraries/generate", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "No POIs" in detail["message"] or "violations" in detail
