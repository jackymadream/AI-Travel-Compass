"""Unit tests for Phase 5.1 POI ingest mapping (no live Overpass)."""

from __future__ import annotations

from scripts.ingest_real_pois import (
    classify_osm_tags,
    elements_to_pois,
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
