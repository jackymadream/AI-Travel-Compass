from src.services.agent_service import AgentService


def test_select_pois_prefers_nightlife_over_temples() -> None:
    service = AgentService()
    pool = [
        {
            "id": "1",
            "name": "Senso-ji Temple",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 90,
            "description": "Historic temple",
            "tags": ["temple", "culture"],
        },
        {
            "id": "2",
            "name": "Tokyo National Museum",
            "category": "attraction",
            "cost_usd": 12,
            "duration_minutes": 120,
            "description": "Museum",
            "tags": ["museum"],
        },
        {
            "id": "3",
            "name": "Golden Gai Bar Hop",
            "category": "food",
            "cost_usd": 20,
            "duration_minutes": 75,
            "description": "Nightlife alley",
            "tags": ["nightlife", "bar"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["nightlife"],
        uncovered_tags={"nightlife"},
    )
    assert selected
    assert selected[0]["name"] == "Golden Gai Bar Hop"
