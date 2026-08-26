from src.services.agent_service import AgentService, _poi_notability_penalty


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


def test_select_pois_avoids_temples_unless_user_requests_temple_or_culture() -> None:
    service = AgentService()
    pool = [
        {
            "id": "1",
            "name": "Historic Temple",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 60,
            "description": "A historic temple",
            # Make sure the old behavior would have matched `preferences=["history"]`.
            "tags": ["temple", "culture", "history"],
        },
        {
            "id": "2",
            "name": "Tokyo National Museum",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 90,
            "description": "Museum history",
            "tags": ["museum", "history"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["history"],
        uncovered_tags={"history"},
    )
    assert selected
    assert selected[0]["name"] == "Tokyo National Museum"


def test_nightlife_day_quota_injects_stop() -> None:
    from src.services.agent_service import (
        _ensure_nightlife_in_selected,
        _nightlife_day_quota_hints,
    )

    selected = [
        {
            "name": "Tokyo Tower",
            "category": "attraction",
            "tags": ["viewpoint"],
            "description": "tower",
            "cost_usd": 18,
        }
    ]
    pool = [
        *selected,
        {
            "name": "Golden Gai",
            "category": "food",
            "tags": ["nightlife", "bar"],
            "description": "tiny bars",
            "cost_usd": 25,
            "source": "signature",
        },
    ]
    forced = _ensure_nightlife_in_selected(
        selected,
        poi_pool=pool,
        used_names=set(),
        preferences=["nightlife"],
    )
    assert any(p["name"] == "Golden Gai" for p in forced)

    hints = _nightlife_day_quota_hints(
        {"activities": [{"poi_name": "Tokyo Tower", "tags": ["viewpoint"]}]},
        preferences=["nightlife"],
        poi_pool=pool,
        used_names=set(),
    )
    assert hints and "nightlife_day_quota" in hints[0]


def test_culture_prefers_architecture_over_temple() -> None:
    """Bare ``culture`` should favor traditional architecture, not worship-only stops."""
    service = AgentService()
    pool = [
        {
            "id": "1",
            "name": "Neighborhood Temple",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 60,
            "description": "A local temple",
            "tags": ["temple", "culture", "shrine"],
        },
        {
            "id": "2",
            "name": "Edo Open Air Architecture",
            "category": "attraction",
            "cost_usd": 8,
            "duration_minutes": 120,
            "description": "Historic wooden buildings",
            "tags": ["architecture", "heritage", "traditional", "culture", "history"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["culture"],
        uncovered_tags={"culture"},
    )
    assert selected
    assert selected[0]["name"] == "Edo Open Air Architecture"


def test_select_pois_pulls_club_from_food_when_user_requests_club() -> None:
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
            "name": "Downtown Club Night",
            "category": "food",
            "cost_usd": 20,
            "duration_minutes": 75,
            "description": "Nightlife club night",
            "tags": ["nightlife", "club"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["club"],
        uncovered_tags={"club"},
    )
    assert selected
    assert selected[0]["name"] == "Downtown Club Night"


def test_select_pois_pulls_pub_from_food_when_user_requests_pub() -> None:
    service = AgentService()
    pool = [
        {
            "id": "1",
            "name": "Historic Temple",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 60,
            "description": "A historic temple",
            "tags": ["temple", "culture"],
        },
        {
            "id": "2",
            "name": "Local Pub Drinks",
            "category": "food",
            "cost_usd": 10,
            "duration_minutes": 60,
            "description": "Casual pub stop",
            "tags": ["food", "pub", "nightlife", "bar"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["pub"],
        uncovered_tags={"pub"},
    )
    assert selected
    assert selected[0]["name"] == "Local Pub Drinks"


def test_notability_penalizes_highway_junction_names() -> None:
    junction = {
        "name": "4-Way Junction",
        "tags": ["highway", "junction"],
        "description": "OSM junction node",
    }
    garden = {
        "name": "Arashiyama Bamboo Grove",
        "tags": ["garden", "nature", "wikipedia", "wikidata:Q1"],
        "description": "Bamboo path",
    }
    assert _poi_notability_penalty(junction) > _poi_notability_penalty(garden)


def test_select_pois_prefers_gardens_for_nature_kid_friendly() -> None:
    service = AgentService()
    pool = [
        {
            "id": "j",
            "name": "4-Way Junction",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 30,
            "description": "Road junction",
            "tags": ["highway", "junction"],
        },
        {
            "id": "g",
            "name": "Arashiyama Bamboo Grove",
            "category": "attraction",
            "cost_usd": 0,
            "duration_minutes": 60,
            "description": "Quiet bamboo garden path",
            "tags": ["garden", "nature", "wikipedia", "family"],
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 0},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["nature", "kid-friendly", "quiet gardens"],
        uncovered_tags={"nature", "kid-friendly"},
    )
    assert selected
    assert selected[0]["name"] == "Arashiyama Bamboo Grove"
