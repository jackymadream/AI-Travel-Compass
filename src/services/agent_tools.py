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
from src.services.itinerary_eval import overlapping_activity_pairs
from src.services.itinerary_i18n import category_photo

# Stable mock city IDs (stand in until a POIs table exists).
MOCK_CITY_TOKYO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MOCK_CITY_SEOUL = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MOCK_SLUG_TO_CITY_ID = {
    "tokyo": MOCK_CITY_TOKYO,
    "seoul": MOCK_CITY_SEOUL,
}

# Minutes added between consecutive activities for transit / walking.
TRAVEL_BUFFER_MINUTES = 30

# Max activities and scheduled minutes by pace (includes required Lunch+Dinner).
PACE_LIMITS: dict[str, dict[str, int]] = {
    "relaxed": {"max_activities": 5, "max_duration_minutes": 420},
    "moderate": {"max_activities": 7, "max_duration_minutes": 600},
    "packed": {"max_activities": 10, "max_duration_minutes": 780},
}

_MOCK_POIS: list[dict[str, Any]] = [
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Senso-ji Temple",
        "category": "attraction",
        "cost_usd": 0,
        "duration_minutes": 90,
        "description": "Historic Buddhist temple in Asakusa with culture-rich streets.",
        "tags": ["culture", "temple", "history", "wikipedia"],
        "lat": 35.7148,
        "lon": 139.7967,
        "address": "Asakusa, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Tokyo National Museum",
        "category": "attraction",
        "cost_usd": 12,
        "duration_minutes": 150,
        "description": "Japan's oldest museum with culture and art collections.",
        "tags": ["museum", "culture", "art", "wikipedia"],
        "lat": 35.7188,
        "lon": 139.7765,
        "address": "Ueno, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "teamLab Planets",
        "category": "attraction",
        "cost_usd": 38,
        "duration_minutes": 120,
        "description": "Immersive digital art museum experience.",
        "tags": ["museum", "art", "nightlife", "wikipedia"],
        "lat": 35.6490,
        "lon": 139.7896,
        "address": "Toyosu, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Shibuya Crossing View",
        "category": "attraction",
        "cost_usd": 0,
        "duration_minutes": 45,
        "description": "Iconic urban scramble crossing and skyline views.",
        "tags": ["urban", "photo", "wikipedia"],
        "lat": 35.6595,
        "lon": 139.7004,
        "address": "Shibuya, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Meiji Shrine",
        "category": "attraction",
        "cost_usd": 0,
        "duration_minutes": 75,
        "description": "Forest shrine dedicated to Emperor Meiji.",
        "tags": ["culture", "shrine", "wikipedia"],
        "lat": 35.6764,
        "lon": 139.6993,
        "address": "Shibuya, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Tokyo Skytree",
        "category": "attraction",
        "cost_usd": 25,
        "duration_minutes": 90,
        "description": "Broadcasting tower with observation decks.",
        "tags": ["urban", "viewpoint", "wikipedia"],
        "lat": 35.7101,
        "lon": 139.8107,
        "address": "Sumida, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ichiran Ramen",
        "category": "food",
        "cost_usd": 14,
        "duration_minutes": 45,
        "description": "Solo-booth tonkotsu ramen — classic Tokyo food stop.",
        "tags": ["food", "ramen"],
        "lat": 35.6612,
        "lon": 139.7010,
        "address": "Shibuya, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Tsukiji Outer Market Breakfast",
        "category": "food",
        "cost_usd": 25,
        "duration_minutes": 75,
        "description": "Fresh seafood stalls and street food near the old market.",
        "tags": ["food", "market", "seafood"],
        "lat": 35.6654,
        "lon": 139.7707,
        "address": "Tsukiji, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ginza Sushi Counter",
        "category": "food",
        "cost_usd": 90,
        "duration_minutes": 90,
        "description": "High-end sushi omakase for food lovers.",
        "tags": ["food", "sushi", "fine-dining"],
        "lat": 35.6717,
        "lon": 139.7649,
        "address": "Ginza, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Ueno Park Cafe Rest",
        "category": "rest",
        "cost_usd": 8,
        "duration_minutes": 60,
        "description": "Quiet park cafe break between museum visits.",
        "tags": ["rest", "park", "cafe"],
        "lat": 35.7146,
        "lon": 139.7714,
        "address": "Ueno, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Onsen Day Spa",
        "category": "rest",
        "cost_usd": 35,
        "duration_minutes": 120,
        "description": "Public bath and rest lounge to recover pace.",
        "tags": ["rest", "onsen", "wellness"],
        "lat": 35.6938,
        "lon": 139.7034,
        "address": "Shinjuku, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_TOKYO,
        "name": "Yoyogi Park Rest",
        "category": "rest",
        "cost_usd": 0,
        "duration_minutes": 60,
        "description": "Wide lawns and forest paths next to Meiji Shrine.",
        "tags": ["rest", "park"],
        "lat": 35.6717,
        "lon": 139.6949,
        "address": "Shibuya, Tokyo",
        "city": "Tokyo",
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Gyeongbokgung Palace",
        "category": "attraction",
        "cost_usd": 5,
        "duration_minutes": 120,
        "description": "Joseon-era palace with culture and history.",
        "tags": ["culture", "palace", "history"],
        "lat": 37.5796,
        "lon": 126.9770,
        "address": "Jongno-gu, Seoul",
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Gwangjang Market",
        "category": "food",
        "cost_usd": 18,
        "duration_minutes": 75,
        "description": "Classic street-food hall for Korean dishes.",
        "tags": ["food", "market"],
        "lat": 37.5700,
        "lon": 126.9996,
        "address": "Jongno-gu, Seoul",
    },
    {
        "city_id": MOCK_CITY_SEOUL,
        "name": "Han River Picnic Rest",
        "category": "rest",
        "cost_usd": 5,
        "duration_minutes": 90,
        "description": "Riverside rest stop with snacks and views.",
        "tags": ["rest", "park"],
        "lat": 37.5285,
        "lon": 126.9326,
        "address": "Yeouido, Seoul",
    },
]


def search_pois_tool(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
) -> list[dict]:
    """
    Query POIs for a city/category (Phase 5.2 live path).

    Prefer Qdrant ``travel_pois`` + Supabase ``pois`` via ``src.tools.search_pois``.
    Fall back to the in-memory mock dataset when live search is empty or
    ``USE_MOCK_POIS=true`` (keeps unit tests / offline planner working).
    """
    from src.tools.search_pois import search_pois, use_mock_pois

    if use_mock_pois():
        return _search_pois_cached_mock(city_id, category, preferences, limit)

    live = search_pois(city_id, category, preferences, limit)
    if live:
        return live
    return _search_pois_cached_mock(city_id, category, preferences, limit)


def _lookup_city_slug(city_id: str) -> str | None:
    """Resolve a live cities.id to slug for mock fallback."""
    try:
        from src.deps import get_supabase

        rows = (
            get_supabase()
            .table("cities")
            .select("slug")
            .eq("id", city_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            return str(rows[0].get("slug") or "").strip().lower() or None
    except Exception:  # noqa: BLE001
        return None
    return None


def _mock_city_id_for(city_id: str) -> str:
    """Map real Tokyo/Seoul UUIDs onto mock pools via slug."""
    if city_id in (MOCK_CITY_TOKYO, MOCK_CITY_SEOUL):
        return city_id
    slug = _lookup_city_slug(city_id)
    if slug and slug in MOCK_SLUG_TO_CITY_ID:
        return MOCK_SLUG_TO_CITY_ID[slug]
    return city_id


def _search_pois_cached_mock(
    city_id: str,
    category: str,
    preferences: list[str],
    limit: int = 5,
) -> list[dict]:
    cache = get_cache_service()
    cache_key = poi_cache_key(city_id, category, preferences, limit) + ":mock"
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
    mock_city_id = _mock_city_id_for(city_id)

    matched: list[tuple[int, dict[str, Any]]] = []
    for poi in _MOCK_POIS:
        if poi["city_id"] != mock_city_id:
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
                "city_id": city_id,
                "id": poi.get("id"),
                "name": poi["name"],
                "category": poi["category"],
                "cost_usd": float(poi["cost_usd"]),
                "duration_minutes": int(poi["duration_minutes"]),
                "description": poi["description"],
                "tags": list(poi.get("tags", [])),
                "lat": poi.get("lat"),
                "lon": poi.get("lon"),
                "address": poi.get("address"),
                "city": poi.get("city"),
                "photo_url": poi.get("photo_url")
                or category_photo(
                    poi["category"],
                    hash(poi["name"]) % 4,
                    city=str(poi.get("city") or "") or None,
                    poi_name=str(poi.get("name") or ""),
                ),
            }
        )
    return results


def evaluate_schedule_and_budget_tool(
    daily_plan: dict,
    daily_budget_usd: float,
    pace: str,
) -> dict:
    """
    Validate one day's draft plan against budget, pace, and meal rules.

    Includes travel buffer time between consecutive activities.
    Requires Lunch + Dinner ``is_food_slot`` activities.
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

    meal_roles = {
        str(a.get("meal_role") or "").strip().lower()
        for a in activities
        if a.get("is_food_slot")
    }
    if "lunch" not in meal_roles or "dinner" not in meal_roles:
        violations.append("MISSING_MEALS: need Lunch and Dinner food slots")
        suggested_adjustments.append(
            "Add is_food_slot Lunch (~12:00) and Dinner (~18:30) with food-type names."
        )

    overlaps = overlapping_activity_pairs(activities)
    if overlaps:
        sample = ", ".join(f"{a} / {b}" for a, b in overlaps[:2])
        violations.append(f"OVERLAPPING_SLOTS: {sample}")
        suggested_adjustments.append(
            "Shift afternoon stops to start after lunch (13:45+) with a 30-minute buffer."
        )

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
