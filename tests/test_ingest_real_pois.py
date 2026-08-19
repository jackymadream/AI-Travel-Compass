"""Unit tests for Phase 5.1 POI ingest mapping (no live Overpass)."""

from __future__ import annotations

from scripts.ingest_real_pois import (
    classify_osm_tags,
    elements_to_pois,
    enrich_poi_description,
    poi_id_from_osm,
    validate_structural,
)
from src.schemas.poi import PoiRecord


def test_classify_osm_tags_attraction_and_food() -> None:
    result = classify_osm_tags({"tourism": "museum", "name": "X"})
    assert result is not None
    cat, tags, cost, duration = result
    assert cat == "attraction"
    assert "museum" in tags
    assert duration >= 60

    result2 = classify_osm_tags({"amenity": "restaurant", "cuisine": "ramen"})
    assert result2 is not None
    cat2, tags2, cost2, _ = result2
    assert cat2 == "food"
    assert cost2 > 0
    assert "ramen" in tags2 or "food" in tags2


def test_elements_to_pois_schema_for_hybrid_agent() -> None:
    elements = [
        {
            "type": "node",
            "id": 1001,
            "lat": 35.71,
            "lon": 139.79,
            "tags": {"name": "Senso-ji", "tourism": "attraction"},
        },
        {
            "type": "node",
            "id": 1002,
            "lat": 35.70,
            "lon": 139.77,
            "tags": {"name": "Ramen Shop", "amenity": "restaurant", "cuisine": "ramen"},
        },
        {
            "type": "node",
            "id": 1003,
            "lat": 35.72,
            "lon": 139.77,
            "tags": {"name": "Ueno Park", "leisure": "park"},
        },
    ]
    pois = elements_to_pois(
        elements,
        city_key="tokyo",
        limit=10,
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        safety_score=4,
    )
    assert len(pois) == 3
    validate_structural(pois)
    assert {p.category for p in pois} == {"attraction", "food", "rest"}
    assert all(isinstance(p, PoiRecord) for p in pois)
    assert pois[0].id == poi_id_from_osm("node", 1001)
    payload = pois[0].qdrant_payload()
    assert payload["city_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert "text" in payload
    assert "POI:" in payload["text"]


def test_elements_skip_obscure_worship_when_attractions_exist() -> None:
    elements = [
        {
            "type": "node",
            "id": 2001,
            "lat": 35.71,
            "lon": 139.79,
            "tags": {"name": "Senso-ji", "tourism": "attraction", "wikidata": "Q235130"},
        },
        {
            "type": "node",
            "id": 2002,
            "lat": 35.67,
            "lon": 139.70,
            "tags": {"name": "Meiji Shrine", "tourism": "attraction", "wikipedia": "en:Meiji Shrine"},
        },
        {
            "type": "node",
            "id": 2003,
            "lat": 35.66,
            "lon": 139.70,
            "tags": {"name": "Tokyo Tower", "tourism": "attraction"},
        },
        {
            "type": "node",
            "id": 2004,
            "lat": 35.71,
            "lon": 139.77,
            "tags": {"name": "Tokyo National Museum", "tourism": "museum"},
        },
        {
            "type": "node",
            "id": 2005,
            "lat": 35.65,
            "lon": 139.79,
            "tags": {"name": "teamLab Planets", "tourism": "gallery"},
        },
        {
            "type": "node",
            "id": 2006,
            "lat": 35.66,
            "lon": 139.70,
            "tags": {"name": "Shibuya Sky", "tourism": "viewpoint"},
        },
        {
            "type": "node",
            "id": 2099,
            "lat": 35.67,
            "lon": 139.70,
            "tags": {"name": "Tenrikyo Harajuku Branch Church", "amenity": "place_of_worship"},
        },
        {
            "type": "node",
            "id": 2100,
            "lat": 35.66,
            "lon": 139.65,
            "tags": {"name": "Ramen Shop", "amenity": "restaurant", "cuisine": "ramen"},
        },
        {
            "type": "node",
            "id": 2101,
            "lat": 35.67,
            "lon": 139.69,
            "tags": {"name": "Yoyogi Park", "leisure": "park"},
        },
    ]
    pois = elements_to_pois(
        elements,
        city_key="tokyo",
        limit=10,
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        safety_score=4,
    )
    names = {p.name for p in pois}
    assert "Tenrikyo Harajuku Branch Church" not in names
    senso = next(p for p in pois if p.name == "Senso-ji")
    assert senso.wikidata == "Q235130"
    assert any(t.startswith("wikidata:") for t in senso.tags)


def test_enrich_poi_description_uses_category_template() -> None:
    text = enrich_poi_description(
        name="Ueno Museum",
        city="Tokyo",
        tags={"tourism": "museum"},
        category="attraction",
    )
    assert "Tokyo" in text
    assert "museum" in text.lower()
    assert " · " not in text or len(text) > 20
