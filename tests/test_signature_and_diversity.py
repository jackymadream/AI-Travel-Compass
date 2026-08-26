"""Tests for curated signature POIs + Approach A diversity helpers."""

from __future__ import annotations

from scripts.ingest_real_pois import (
    classify_osm_tags,
    element_lat_lon,
    elements_to_pois,
    worship_soft_tags,
)
from src.services.agent_service import (
    AgentService,
    _geo_cluster_selected_pois,
    _soft_preference_coverage_hints,
)
from src.services.signature_pois import (
    build_signature_pois,
    merge_signature_and_overpass,
    names_near_duplicate,
)
from src.schemas.poi import PoiRecord
from src.tools.search_pois import mmr_select

SIGNATURE_THEME_TAGS = ("nightlife", "museum", "art", "family", "park", "viewpoint")
SIGNATURE_CITIES = (
    "tokyo",
    "osaka",
    "kyoto",
    "seoul",
    "paris",
    "rome",
    "barcelona",
    "bangkok",
    "london",
    "marrakech",
    "reykjavik",
)


def test_signature_cities_load_diverse_themes() -> None:
    for slug in SIGNATURE_CITIES:
        pois = build_signature_pois(
            city_slug=slug,
            city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            city_display=slug.title(),
        )
        assert len(pois) >= 20, slug
        assert all(p.source == "signature" for p in pois), slug
        tags = {t for p in pois for t in p.tags}
        for need in SIGNATURE_THEME_TAGS:
            assert need in tags, f"{slug} missing {need}"


def test_tokyo_signatures_include_shibuya_neighborhood() -> None:
    pois = build_signature_pois(
        city_slug="tokyo",
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        city_display="Tokyo",
    )
    neighborhoods = {
        t.split(":", 1)[-1]
        for p in pois
        for t in p.tags
        if str(t).startswith("neighborhood:")
    }
    assert "Shibuya" in neighborhoods or "shibuya" in {n.lower() for n in neighborhoods}


def test_merge_signature_dedupes_overpass_by_name() -> None:
    sigs = build_signature_pois(
        city_slug="tokyo",
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        city_display="Tokyo",
    )[:3]
    dup = PoiRecord(
        id="overpass-dup",
        name=sigs[0].name,
        city="Tokyo",
        category=sigs[0].category,
        description="dup",
        lat=sigs[0].lat,
        lon=sigs[0].lon,
        price_level=1,
        rating=4.0,
        safety_score=3,
        city_id=sigs[0].city_id,
        tags=["overpass"],
        cost_usd=0,
        duration_minutes=60,
        source="overpass",
    )
    other = PoiRecord(
        id="overpass-other",
        name="Unique Overpass Cafe",
        city="Tokyo",
        category="food",
        description="cafe",
        lat=35.66,
        lon=139.70,
        price_level=1,
        rating=4.0,
        safety_score=3,
        city_id=sigs[0].city_id,
        tags=["food", "cafe"],
        cost_usd=10,
        duration_minutes=45,
        source="overpass",
    )
    merged = merge_signature_and_overpass(sigs, [dup, other])
    names = [p.name for p in merged]
    assert names.count(sigs[0].name) == 1
    assert "Unique Overpass Cafe" in names
    assert names_near_duplicate("Senso-ji Temple", "senso-ji temple")


def test_worship_soft_tags_religion_aware() -> None:
    buddhist = worship_soft_tags({"religion": "buddhist", "name": "X Temple"})
    assert "temple" in buddhist
    assert "church" not in buddhist

    church = worship_soft_tags({"religion": "christian", "building": "church"})
    assert "church" in church
    assert "temple" not in church

    shrine = worship_soft_tags({"religion": "shinto", "name": "Meiji Jingu"})
    assert "shrine" in shrine

    classified = classify_osm_tags(
        {"amenity": "place_of_worship", "religion": "christian", "name": "St Mary"}
    )
    assert classified is not None
    _cat, tags, _cost, _dur = classified
    assert "church" in tags
    assert "temple" not in tags


def test_elements_to_pois_accepts_way_center() -> None:
    elements = [
        {
            "type": "way",
            "id": 9001,
            "center": {"lat": 35.71, "lon": 139.77},
            "tags": {"name": "Ueno Park Grounds", "leisure": "park"},
        },
        {
            "type": "node",
            "id": 9002,
            "lat": 35.70,
            "lon": 139.76,
            "tags": {"name": "Ramen Spot", "amenity": "restaurant"},
        },
        {
            "type": "node",
            "id": 9003,
            "lat": 35.69,
            "lon": 139.75,
            "tags": {"name": "City Museum", "tourism": "museum"},
        },
    ]
    assert element_lat_lon(elements[0]) == (35.71, 139.77)
    pois = elements_to_pois(
        elements,
        city_key="tokyo",
        limit=10,
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        safety_score=4,
    )
    names = {p.name for p in pois}
    assert "Ueno Park Grounds" in names
    park = next(p for p in pois if p.name == "Ueno Park Grounds")
    assert park.osm_type == "way"


def test_mmr_select_spreads_tags() -> None:
    candidates = [
        {"name": "A", "tags": ["museum", "art"], "description": "museum art"},
        {"name": "B", "tags": ["museum"], "description": "museum"},
        {"name": "C", "tags": ["nightlife", "bar"], "description": "nightlife bar"},
        {"name": "D", "tags": ["park", "nature"], "description": "park nature"},
    ]
    picked = mmr_select(candidates, limit=3, preferences=["museum", "nightlife", "nature"])
    assert len(picked) == 3
    tag_blob = " ".join(" ".join(p["tags"]) for p in picked)
    assert "nightlife" in tag_blob or "park" in tag_blob


def test_soft_coverage_hints_when_unused_match_exists() -> None:
    draft = {
        "activities": [
            {
                "poi_name": "Tokyo Tower",
                "category": "attraction",
                "description": "viewpoint",
                "tags": ["viewpoint"],
            }
        ]
    }
    pool = [
        {
            "name": "Tokyo Tower",
            "category": "attraction",
            "tags": ["viewpoint"],
            "description": "tower",
        },
        {
            "name": "Golden Gai",
            "category": "food",
            "tags": ["nightlife", "bar"],
            "description": "bars",
            "source": "signature",
        },
    ]
    hints = _soft_preference_coverage_hints(
        draft,
        uncovered_tags={"nightlife"},
        poi_pool=pool,
        used_names=set(),
    )
    assert hints
    assert "nightlife" in hints[0]


def test_geo_cluster_swaps_far_outlier() -> None:
    selected = [
        {
            "name": "Near A",
            "category": "attraction",
            "lat": 35.66,
            "lon": 139.70,
            "tags": ["neighborhood:Shibuya"],
            "cost_usd": 0,
        },
        {
            "name": "Far B",
            "category": "attraction",
            "lat": 35.71,
            "lon": 139.88,
            "tags": ["neighborhood:Sumida"],
            "cost_usd": 0,
        },
    ]
    pool = [
        *selected,
        {
            "name": "Near C",
            "category": "attraction",
            "lat": 35.661,
            "lon": 139.701,
            "tags": ["neighborhood:Shibuya"],
            "cost_usd": 0,
        },
    ]
    clustered = _geo_cluster_selected_pois(
        selected, poi_pool=pool, used_names=set(), max_km=3.0
    )
    names = {p["name"] for p in clustered}
    assert "Near A" in names
    assert "Near C" in names
    assert "Far B" not in names


def test_select_still_works_with_geo_cluster() -> None:
    service = AgentService()
    pool = [
        {
            "id": "1",
            "name": "Museum A",
            "category": "attraction",
            "cost_usd": 10,
            "duration_minutes": 90,
            "description": "art museum",
            "tags": ["art", "museum", "neighborhood:Ueno"],
            "lat": 35.71,
            "lon": 139.77,
        },
        {
            "id": "2",
            "name": "Park B",
            "category": "rest",
            "cost_usd": 0,
            "duration_minutes": 60,
            "description": "park",
            "tags": ["park", "nature", "neighborhood:Ueno"],
            "lat": 35.712,
            "lon": 139.772,
        },
    ]
    selected = service._select_pois_for_day(
        poi_pool=pool,
        counts={"attraction": 1, "food": 0, "rest": 1},
        used_names=set(),
        day_number=1,
        prefer_cheap=False,
        budget=100,
        preferences=["art", "nature"],
        uncovered_tags={"art", "nature"},
    )
    assert len(selected) == 2
