"""
Core tool execution for the Phase 3 itinerary agent.

See docs/AGENT_ARCHITECTURE.md:
  POI Retrieval Tool · Schedule Evaluator Tool
"""

from __future__ import annotations

from typing import Any

from src.services.cache_service import (
    TTL_POI_SECONDS,
    get_cache_service,
    poi_cache_key,
)

# Stable mock city IDs (stand in until a POIs table exists).
MOCK_CITY_TOKYO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MOCK_CITY_SEOUL = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# Minutes added between consecutive activities for transit / walking.
TRAVEL_BUFFER_MINUTES = 30

# Max activities (excl. none) and max scheduled minutes (activity + buffers) by pace.
PACE_LIMITS: dict[str, dict[str, int]] = {
    "relaxed": {"max_activities": 3, "max_duration_minutes": 360},
    "moderate": {"max_activities": 5, "max_duration_minutes": 540},
    "packed": {"max_activities": 8, "max_duration_minutes": 720},
}

_MOCK_POIS: list[dict[str, Any]] = [
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Senso-ji Temple",
        "category": "attraction",
        "cost_usd": 0,
        "duration_minutes": 90,
        "description": "Historic Buddhist temple in Asakusa with culture-rich streets.",
        "tags": ["culture", "temple", "history"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Tokyo National Museum",
        "category": "attraction",
        "cost_usd": 12,
        "duration_minutes": 150,
        "description": "Japan's oldest museum with culture and art collections.",
        "tags": ["museum", "culture", "art"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "teamLab Planets",
        "category": "attraction",
        "cost_usd": 38,
        "duration_minutes": 120,
        "description": "Immersive digital art museum experience.",
        "tags": ["museum", "art", "nightlife"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Shibuya Crossing View",
        "category": "attraction",
        "cost_usd": 0,
        "duration_minutes": 45,
        "description": "Iconic urban scramble crossing and skyline views.",
        "tags": ["urban", "photo"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ichiran Ramen",
        "category": "food",
        "cost_usd": 14,
        "duration_minutes": 45,
        "description": "Solo-booth tonkotsu ramen — classic Tokyo food stop.",
        "tags": ["food", "ramen"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Tsukiji Outer Market Breakfast",
        "category": "food",
        "cost_usd": 25,
        "duration_minutes": 75,
        "description": "Fresh seafood stalls and street food near the old market.",
        "tags": ["food", "market", "seafood"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ginza Sushi Counter",
        "category": "food",
        "cost_usd": 90,
        "duration_minutes": 90,
        "description": "High-end sushi omakase for food lovers.",
        "tags": ["food", "sushi", "fine-dining"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ueno Park Cafe Rest",
        "category": "rest",
        "cost_usd": 8,
        "duration_minutes": 60,
        "description": "Quiet park cafe break between museum visits.",
        "tags": ["rest", "park", "cafe"],
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Onsen Day Spa",
        "category": "rest",
        "cost_usd": 35,
        "duration_minutes": 120,
        "description": "Public bath and rest lounge to recover pace.",
        "tags": ["rest", "onsen", "wellness"],
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Gyeongbokgung Palace",
        "category": "attraction",
        "cost_usd": 5,
        "duration_minutes": 120,
        "description": "Joseon-era palace with culture and history.",
        "tags": ["culture", "palace", "history"],
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Gwangjang Market",
        "category": "food",
        "cost_usd": 18,
        "duration_minutes": 75,
        "description": "Classic street-food hall for Korean dishes.",
        "tags": ["food", "market"],
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Han River Picnic Rest",
        "category": "rest",
        "cost_usd": 5,
        "duration_minutes": 90,
        "description": "Riverside rest stop with snacks and views.",
        "tags": ["rest", "park"],
    },
]


def search_pois_tool(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
) -> list[dict]:
    """
    Query POIs from the mock dataset filtered by ``city_id`` and ``category``.

    Preference tokens boost ranking when they appear in tags, name, or description.
    Each result includes name, category, cost_usd, duration_minutes, description.
    Results are cached for 7 days (Redis or in-memory fallback).
    """
    cache = get_cache_service()
    cache_key = poi_cache_key(city_id, category, preferences, limit)
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    results = _search_pois_uncached(city_id, category, preferences, limit)
    cache.set(cache_key, results, ttl_seconds=TTL_POI_SECONDS)
    return results


def _search_pois_uncached(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
) -> list[dict]:
    """POI lookup without cache — used on miss and in tests that patch this path."""
    category_norm = (category or "").strip().lower()
    prefs = [p.strip().lower() for p in preferences if p and p.strip()]

    matched: list[tuple[int, dict[str, Any]]] = []
    for poi in _MOCK_POIS:
        if poi["city_id"] != city_id:
            continue
        if poi["category"] != category_norm:
            continue
        score = _preference_score(poi, prefs)
        matched.append((score, poi))

    matched.sort(key=lambda item: (-item[0], item[1]["name"]))

    results: list[dict] = []
    for _score, poi in matched[: max(0, limit)]:
        results.append(
            {
                "city_id": poi["city_id"],
                "name": poi["name"],
                "category": poi["category"],
                "cost_usd": float(poi["cost_usd"]),
                "duration_minutes": int(poi["duration_minutes"]),
                "description": poi["description"],
                "tags": list(poi.get("tags", [])),
            }
        )
    return results


def evaluate_schedule_and_budget_tool(
    daily_plan: dict,
    daily_budget_usd: float,
    pace: str,
) -> dict:
    """
    Validate one day's draft plan against budget and pace.

    Includes travel buffer time between consecutive activities.
    Returns ``is_valid``, ``violations``, ``suggested_adjustments``, plus totals.
    """
    activities = list(daily_plan.get("activities") or [])
    pace_key = (pace or "").strip().lower()
    limits = PACE_LIMITS.get(pace_key)

    total_cost = sum(float(a.get("cost_usd") or 0) for a in activities)
    activity_minutes = sum(int(a.get("duration_minutes") or 0) for a in activities)
    hops = max(0, len(activities) - 1)
    buffer_minutes = hops * TRAVEL_BUFFER_MINUTES
    total_duration = activity_minutes + buffer_minutes

    violations: list[str] = []
    suggested_adjustments: list[str] = []

    if daily_budget_usd is not None and total_cost > daily_budget_usd:
        over_by = total_cost - daily_budget_usd
        # Format without trailing .0 when whole dollars.
        over_label = (
            f"${over_by:.0f}" if float(over_by).is_integer() else f"${over_by:.2f}"
        )
        violations.append(f"Over budget by {over_label}")
        suggested_adjustments.append(
            "Replace a high-cost activity with a cheaper food or free attraction."
        )

    if limits is None:
        violations.append(f"Unknown pace '{pace}'")
        suggested_adjustments.append(
            "Use pace 'relaxed', 'moderate', or 'packed'."
        )
    else:
        max_acts = limits["max_activities"]
        max_mins = limits["max_duration_minutes"]
        if len(activities) > max_acts:
            violations.append(
                f"Schedule too packed for {pace_key} pace "
                f"({len(activities)} activities; max {max_acts})"
            )
            suggested_adjustments.append(
                f"Remove {len(activities) - max_acts} activity(ies) or switch to a denser pace."
            )
        if total_duration > max_mins:
            violations.append(
                f"Schedule too packed for {pace_key} pace "
                f"({total_duration} minutes including travel; max {max_mins})"
            )
            suggested_adjustments.append(
                "Shorten activity durations or drop one stop to leave buffer time."
            )

    is_valid = len(violations) == 0
    if is_valid and not suggested_adjustments:
        suggested_adjustments = []

    return {
        "is_valid": is_valid,
        "violations": violations,
        "suggested_adjustments": suggested_adjustments,
        "total_cost_usd": float(total_cost),
        "total_duration_minutes": int(total_duration),
        "activity_minutes": int(activity_minutes),
        "travel_buffer_minutes": int(buffer_minutes),
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
