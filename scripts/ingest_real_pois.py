#!/usr/bin/env python3
"""
Phase 5.1 — Real global POI ingestion (Overpass → optional Places → schema).

ETL flow
--------
1. Query OpenStreetMap Overpass API for a target city bbox.
2. Map OSM tags → Travel Compass POI schema (attraction | food | rest).
3. Optionally enrich with Google Places Text Search
   (rating, user_ratings_total, primary_type, price_level) when
   GOOGLE_PLACES_API_KEY is set.
4. Unless --dry-run: upsert to Supabase ``pois``, embed with Vertex
   text-embedding-004 via ``src.services.embedding``, upsert vectors into
   Qdrant ``travel_pois`` via ``src.services.qdrant_service``.

Usage
-----
  # Structural dry-run (Overpass only — no Supabase / Vertex / Qdrant writes)
  python scripts/ingest_real_pois.py --city tokyo --limit 10 --dry-run

  # Full ingest (requires .env + pois table; see scripts/migrate_add_pois.sql)
  python scripts/ingest_real_pois.py --city tokyo --limit 100
  python scripts/ingest_real_pois.py --city london --limit 50 --skip-places
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.schemas.poi import PoiRecord  # noqa: E402
from src.services.embedding import (  # noqa: E402
    EmbeddingServiceError,
    embed_documents,
    embedding_dimensions,
)
from src.services.qdrant_service import (  # noqa: E402
    QdrantServiceError,
    upsert_poi_vectors,
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
USER_AGENT = "GenAI-Travel-Compass/0.1 (poi-ingest; contact=travel.jackymadream.com)"

# south, west, north, east — compact central bboxes for dense tourism POIs
CITY_REGISTRY: dict[str, dict[str, Any]] = {
    "tokyo": {
        "slug": "tokyo",
        "iso": "JP",
        "display_name": "Tokyo",
        # Wider metro coverage: Shibuya–Asakusa–Odaiba–Mitaka fringe
        "bbox": (35.60, 139.55, 35.78, 139.90),
    },
    "london": {
        "slug": "london",
        "iso": "GB",
        "display_name": "London",
        "bbox": (51.48, -0.20, 51.55, -0.05),
    },
    "seoul": {
        "slug": "seoul",
        "iso": "KR",
        "display_name": "Seoul",
        "bbox": (37.52, 126.92, 37.60, 127.05),
    },
}

# OSM tag → Travel Compass category + soft tags + default cost/duration
OSM_CATEGORY_RULES: list[tuple[str, str, str, list[str], float, int]] = [
    # (key, value, category, tags, cost_usd, duration_minutes)
    ("tourism", "attraction", "attraction", ["attraction", "sightseeing"], 0, 90),
    ("tourism", "museum", "attraction", ["museum", "culture"], 12, 120),
    ("tourism", "gallery", "attraction", ["museum", "art"], 10, 90),
    ("tourism", "viewpoint", "attraction", ["viewpoint", "photo"], 0, 45),
    ("tourism", "zoo", "attraction", ["zoo", "family"], 20, 150),
    ("historic", "monument", "attraction", ["history", "monument"], 0, 45),
    ("historic", "castle", "attraction", ["history", "castle"], 15, 120),
    ("amenity", "place_of_worship", "attraction", ["culture"], 0, 60),
    ("amenity", "restaurant", "food", ["food", "restaurant"], 25, 75),
    ("amenity", "cafe", "food", ["food", "cafe"], 10, 45),
    ("amenity", "fast_food", "food", ["food", "fast-food"], 8, 30),
    ("amenity", "bar", "food", ["food", "nightlife", "bar"], 18, 60),
    ("amenity", "pub", "food", ["food", "pub", "nightlife"], 16, 60),
    ("amenity", "nightclub", "food", ["nightlife", "club"], 25, 90),
    ("leisure", "park", "rest", ["rest", "park"], 0, 60),
    ("leisure", "garden", "rest", ["rest", "garden"], 0, 60),
    ("amenity", "spa", "rest", ["rest", "wellness"], 35, 120),
    ("tourism", "theme_park", "attraction", ["theme-park", "family"], 40, 240),
]

PLACES_PRICE_MAP = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

# Keep obscure neighborhood churches out unless the city would miss this floor.
MIN_ATTRACTION = 6

# Soft theme floors before round-robin truncate (best-effort).
THEME_QUOTAS: dict[str, int] = {
    "museum": 3,
    "nightlife": 4,
    "park": 2,
    "garden": 1,
    "viewpoint": 2,
    "family": 2,
}


def worship_soft_tags(tags: dict[str, str]) -> list[str]:
    """Religion-aware tags for place_of_worship (avoid blanket ``temple``)."""
    religion = str(tags.get("religion") or "").strip().lower()
    building = str(tags.get("building") or "").strip().lower()
    name = str(tags.get("name:en") or tags.get("name") or "").lower()
    out = ["culture"]
    if religion in {"buddhist", "buddhism"} or "temple" in name or building == "temple":
        out.extend(["temple", "buddhist"])
    elif religion in {"shinto"} or "jingu" in name or "jinja" in name or "shrine" in name:
        out.extend(["shrine", "shinto"])
    elif religion in {"christian", "catholic", "protestant", "orthodox"} or building == "church":
        out.extend(["church", "christian"])
    elif religion in {"jewish"} or "synagogue" in name:
        out.extend(["synagogue"])
    elif religion in {"muslim", "islam"} or "mosque" in name:
        out.extend(["mosque"])
    else:
        out.append("worship")
    return list(dict.fromkeys(out))


CATEGORY_BLURBS: dict[str, str] = {
    "museum": "A notable museum in {city}. Budget 1–2 hours for the main galleries.",
    "gallery": "An art gallery stop in {city} — short visit, good for a cultural pause.",
    "attraction": "A signature sightseeing stop in {city} worth adding to your walking day.",
    "viewpoint": "An observation or viewpoint in {city}. Go early or near sunset for clearer views.",
    "place_of_worship": (
        "A local place of worship in {city}. Dress modestly, keep voices low, and check visiting hours."
    ),
    "restaurant": "A sit-down food stop in {city}. Expect a short wait at peak meal times.",
    "cafe": "A cafe break in {city} — useful as a rest between walking segments.",
    "bar": "An evening nightlife stop in {city}. Some venues have cover charges or ID checks.",
    "pub": "A casual pub stop in {city} for drinks and a slower evening pace.",
    "nightclub": "A late-night music venue in {city}. Check door policy and last-entry times.",
    "park": "A green rest stop in {city} to reset between attractions.",
    "garden": "A garden stroll in {city} — quieter than the main sightseeing spine.",
    "spa": "A wellness / spa pause in {city}. Book ahead when you can.",
    "castle": "A historic castle or fortification in {city}. Allow extra time for queues.",
    "monument": "A landmark monument in {city} — usually a short photo stop.",
}


def enrich_poi_description(
    *,
    name: str,
    city: str,
    tags: dict[str, Any],
    category: str,
) -> str:
    raw = str(tags.get("description") or "").strip()
    if len(raw) >= 40:
        return raw[:2000]
    kind = str(
        tags.get("tourism")
        or tags.get("amenity")
        or tags.get("historic")
        or tags.get("leisure")
        or category
    )
    template = CATEGORY_BLURBS.get(kind) or (
        "A {category} stop in {city} that fits a walking itinerary."
    )
    blurb = template.format(city=city, category=category, name=name)
    extras = [
        str(tags.get("cuisine") or "").strip(),
        f"Also known as {tags['name:en']}" if tags.get("name:en") and tags.get("name:en") != name else "",
    ]
    suffix = " ".join(bit for bit in extras if bit)
    text = f"{blurb} {suffix}".strip()
    return text[:2000]


def load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def poi_id_from_osm(osm_type: str, osm_id: int) -> str:
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"travel-compass:poi:osm:{osm_type}:{osm_id}")
    )


def classify_osm_tags(tags: dict[str, str]) -> tuple[str, list[str], float, int] | None:
    for key, value, category, soft_tags, cost, duration in OSM_CATEGORY_RULES:
        if tags.get(key) == value:
            extra = [t for t in (tags.get("cuisine"), tags.get("tourism"), tags.get("amenity")) if t]
            merged = list(dict.fromkeys([*soft_tags, *extra]))
            if key == "amenity" and value == "place_of_worship":
                merged = list(dict.fromkeys([*worship_soft_tags(tags), *extra]))
            return category, merged, cost, duration
    return None


_JUNCTION_NAME_RE = re.compile(r"(?i)\b(?:\d+|n|t)[\s-]*way\s+junction\b")


def is_osm_junction_poi(tags: dict[str, str], name: str) -> bool:
    """True for highway/junction OSM nodes and N-Way / T-Way junction names."""
    if tags.get("highway") or tags.get("junction"):
        return True
    return bool(_JUNCTION_NAME_RE.search(name or ""))


def build_overpass_query(bbox: tuple[float, float, float, float], limit: int) -> str:
    """Build Overpass QL for nodes, ways, and relations in the city bbox."""
    south, west, north, east = bbox
    out_cap = max(limit * 10, 120)
    parts: list[str] = []
    for key, value, *_ in OSM_CATEGORY_RULES:
        parts.append(f'  node["{key}"="{value}"]({south},{west},{north},{east});')
        parts.append(f'  way["{key}"="{value}"]({south},{west},{north},{east});')
        parts.append(f'  relation["{key}"="{value}"]({south},{west},{north},{east});')
    filters = "\n".join(parts)
    return f"""
[out:json][timeout:120];
(
{filters}
);
out center {out_cap};
""".strip()


def element_lat_lon(el: dict[str, Any]) -> tuple[float | None, float | None]:
    """Node lat/lon, or way/relation center from ``out center``."""
    if el.get("lat") is not None and el.get("lon") is not None:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center")
    if isinstance(center, dict) and center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    return None, None


def fetch_overpass_elements(
    city_key: str,
    *,
    limit: int,
    timeout: float = 90.0,
) -> list[dict[str, Any]]:
    meta = CITY_REGISTRY[city_key]
    query = build_overpass_query(meta["bbox"], limit)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        payload = response.json()

    elements = payload.get("elements") or []
    if not isinstance(elements, list):
        raise RuntimeError("Unexpected Overpass response: missing elements list")
    return elements


def format_address(tags: dict[str, str]) -> str | None:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:suburb") or tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    cleaned = [p for p in parts if p]
    return ", ".join(cleaned) if cleaned else tags.get("addr:full")


def _poi_record_from_element(
    el: dict[str, Any],
    *,
    name: str,
    display: str,
    category: str,
    soft_tags: list[str],
    cost: float,
    duration: int,
    city_id: str | None,
    safety_score: int,
    wiki_qid: str,
) -> PoiRecord:
    tags = el.get("tags") or {}
    osm_id = int(el["id"])
    osm_type = str(el.get("type") or "node")
    lat, lon = element_lat_lon(el)
    description = enrich_poi_description(
        name=name, city=display, tags=tags, category=category
    )
    en_name = str(tags.get("name:en") or "").strip()
    if en_name and en_name not in soft_tags:
        soft_tags = list(dict.fromkeys([*soft_tags, f"name_en:{en_name}"]))
    if "wikipedia" in tags or tags.get("wikidata"):
        soft_tags = list(dict.fromkeys([*soft_tags, "popular", "wikipedia"]))
    return PoiRecord(
        id=poi_id_from_osm(osm_type, osm_id),
        name=name,
        city=display,
        category=category,  # type: ignore[arg-type]
        description=description[:2000],
        lat=lat,
        lon=lon,
        price_level=0 if cost <= 0 else (1 if cost < 15 else 2 if cost < 40 else 3),
        rating=None,
        safety_score=safety_score,
        city_id=city_id,
        tags=soft_tags,
        cost_usd=float(cost),
        duration_minutes=int(duration),
        address=format_address({str(k): str(v) for k, v in tags.items()}),
        source="overpass",
        osm_type=osm_type,
        osm_id=osm_id,
        wikidata=wiki_qid or None,
    )


def _theme_hits(poi: PoiRecord) -> set[str]:
    tags = {str(t).lower() for t in poi.tags}
    hits: set[str] = set()
    for theme in THEME_QUOTAS:
        if theme in tags or any(theme in t for t in tags):
            hits.add(theme)
    return hits


def _apply_theme_quotas(
    by_category: dict[str, list[PoiRecord]],
    *,
    limit: int,
) -> dict[str, list[PoiRecord]]:
    """Promote theme-diverse POIs toward the front of each category bucket."""
    promoted: dict[str, list[PoiRecord]] = {
        "attraction": [],
        "food": [],
        "rest": [],
    }
    theme_counts = {t: 0 for t in THEME_QUOTAS}
    remaining: dict[str, list[PoiRecord]] = {k: list(v) for k, v in by_category.items()}

    # First pass: pull under-quota theme matches.
    for category in ("attraction", "food", "rest"):
        kept: list[PoiRecord] = []
        deferred: list[PoiRecord] = []
        for poi in remaining[category]:
            hits = _theme_hits(poi)
            needed = [t for t in hits if theme_counts.get(t, 0) < THEME_QUOTAS.get(t, 0)]
            if needed and len(promoted[category]) < max(limit, 10):
                promoted[category].append(poi)
                for t in needed:
                    theme_counts[t] = theme_counts.get(t, 0) + 1
            else:
                deferred.append(poi)
        remaining[category] = deferred

    for category in ("attraction", "food", "rest"):
        promoted[category].extend(remaining[category])
        promoted[category] = promoted[category][: max(limit, 10)]
    return promoted


def elements_to_pois(
    elements: list[dict[str, Any]],
    *,
    city_key: str,
    limit: int,
    city_id: str | None,
    safety_score: int,
) -> list[PoiRecord]:
    meta = CITY_REGISTRY[city_key]
    display = meta["display_name"]
    seen_names: set[str] = set()
    deferred_worship: list[PoiRecord] = []
    by_category: dict[str, list[PoiRecord]] = {
        "attraction": [],
        "food": [],
        "rest": [],
    }

    for el in elements:
        osm_type = str(el.get("type") or "")
        if osm_type not in {"node", "way", "relation"}:
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        lat, lon = element_lat_lon(el)
        if lat is None or lon is None:
            continue
        tag_map = {str(k): str(v) for k, v in tags.items()}
        if is_osm_junction_poi(tag_map, name):
            continue
        classified = classify_osm_tags(tag_map)
        if not classified:
            continue
        category, soft_tags, cost, duration = classified
        wiki_qid = str(tags.get("wikidata") or "").strip()
        has_wiki = bool(tags.get("wikipedia") or wiki_qid)
        obscure_worship = (
            tags.get("amenity") == "place_of_worship"
            and not has_wiki
            and not tags.get("tourism")
        )
        if wiki_qid:
            soft_tags = list(dict.fromkeys([*soft_tags, f"wikidata:{wiki_qid}", "wikipedia"]))
        elif tags.get("wikipedia"):
            soft_tags = list(dict.fromkeys([*soft_tags, "wikipedia"]))
        record = _poi_record_from_element(
            el,
            name=name,
            display=display,
            category=category,
            soft_tags=soft_tags,
            cost=cost,
            duration=duration,
            city_id=city_id,
            safety_score=safety_score,
            wiki_qid=wiki_qid,
        )
        if obscure_worship:
            deferred_worship.append(record)
            seen_names.add(name.lower())
            continue
        # Cap per category while scanning so we do not hold tens of thousands of records.
        if len(by_category[category]) >= max(limit * 2, 20):
            continue
        seen_names.add(name.lower())
        by_category[category].append(record)
        if all(len(by_category[c]) >= max(limit * 2, 20) for c in by_category):
            break

    need = max(0, MIN_ATTRACTION - len(by_category["attraction"]))
    for rec in deferred_worship:
        if need <= 0:
            break
        by_category["attraction"].append(rec)
        need -= 1

    by_category = _apply_theme_quotas(by_category, limit=limit)

    # Round-robin categories so agent tools get attraction/food/rest coverage.
    pois: list[PoiRecord] = []
    buckets = [by_category["attraction"], by_category["food"], by_category["rest"]]
    index = 0
    while len(pois) < limit and any(buckets):
        bucket = buckets[index % len(buckets)]
        index += 1
        if not bucket:
            continue
        pois.append(bucket.pop(0))
    return pois


def enrich_with_places(
    pois: list[PoiRecord],
    *,
    api_key: str,
    timeout: float = 30.0,
) -> list[PoiRecord]:
    """Attach Places rating / primary_type / price_level when available."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.name,places.photos,places.displayName,places.rating,"
            "places.userRatingCount,places.primaryType,places.priceLevel,"
            "places.formattedAddress"
        ),
        "User-Agent": USER_AGENT,
    }
    enriched: list[PoiRecord] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for poi in pois:
            text_query = f"{poi.name} {poi.city}"
            body: dict[str, Any] = {"textQuery": text_query, "pageSize": 1}
            if poi.lat is not None and poi.lon is not None:
                body["locationBias"] = {
                    "circle": {
                        "center": {"latitude": poi.lat, "longitude": poi.lon},
                        "radius": 500.0,
                    }
                }
            try:
                response = client.post(PLACES_SEARCH_URL, json=body)
                if response.status_code >= 400:
                    print(
                        f"  Places skip {poi.name!r}: HTTP {response.status_code}",
                        file=sys.stderr,
                    )
                    enriched.append(poi)
                    time.sleep(0.15)
                    continue
                places = (response.json() or {}).get("places") or []
            except httpx.HTTPError as exc:
                print(f"  Places skip {poi.name!r}: {exc}", file=sys.stderr)
                enriched.append(poi)
                continue

            if not places:
                enriched.append(poi)
                time.sleep(0.15)
                continue

            place = places[0]
            price_raw = place.get("priceLevel")
            price_level = PLACES_PRICE_MAP.get(str(price_raw), poi.price_level)
            updates: dict[str, Any] = {
                "rating": place.get("rating", poi.rating),
                "user_ratings_total": place.get("userRatingCount", poi.user_ratings_total),
                "primary_type": place.get("primaryType", poi.primary_type),
                "price_level": price_level,
                "google_place_name": str(place.get("name") or "").strip() or poi.google_place_name,
                "source": "overpass+places",
            }
            photos = place.get("photos") or []
            if isinstance(photos, list) and photos:
                first_photo = photos[0] if isinstance(photos[0], dict) else {}
                photo_name = str(first_photo.get("name") or "").strip()
                if photo_name:
                    updates["google_photo_name"] = photo_name
            addr = place.get("formattedAddress")
            if addr:
                updates["address"] = addr
            enriched.append(poi.model_copy(update=updates))
            time.sleep(0.15)

    return enriched


def resolve_city_row(supabase: Any, city_key: str) -> dict[str, Any] | None:
    meta = CITY_REGISTRY[city_key]
    slug = meta["slug"]
    iso = meta["iso"]
    countries = (
        supabase.table("countries").select("id, iso_code").eq("iso_code", iso).execute()
    )
    rows = countries.data or []
    if not rows:
        return None
    country_id = rows[0]["id"]
    cities = (
        supabase.table("cities")
        .select("id, slug, safety_index, name")
        .eq("country_id", country_id)
        .eq("slug", slug)
        .execute()
    )
    city_rows = cities.data or []
    return city_rows[0] if city_rows else None


def upsert_supabase_pois(supabase: Any, pois: list[PoiRecord]) -> int:
    rows = [p.supabase_row() for p in pois]
    # PostgREST upsert on primary key
    try:
        supabase.table("pois").upsert(rows, on_conflict="id").execute()
    except Exception as exc:  # noqa: BLE001
        # photo_url column is optional until migrate_poi_photo_url.sql is applied.
        msg = str(exc).lower()
        if "photo_url" in msg:
            for row in rows:
                row.pop("photo_url", None)
            supabase.table("pois").upsert(rows, on_conflict="id").execute()
        else:
            raise
    return len(rows)


def upsert_qdrant_pois(pois: list[PoiRecord]) -> int:
    texts = [p.embedding_text() for p in pois]
    vectors = embed_documents(texts)
    records = [
        {"id": p.id, "payload": p.qdrant_payload()}
        for p in pois
    ]
    return upsert_poi_vectors(records, vectors)


def validate_structural(pois: list[PoiRecord]) -> None:
    """Ensure records match Phase 5.1 + agent-friendly fields."""
    required = (
        "id",
        "name",
        "city",
        "category",
        "description",
        "lat",
        "lon",
        "price_level",
        "rating",
        "safety_score",
    )
    if not pois:
        raise RuntimeError("No POIs extracted — check Overpass / city bbox.")
    for poi in pois:
        data = poi.model_dump()
        for key in required:
            if key not in data:
                raise RuntimeError(f"Missing field {key} on POI {poi.name!r}")
        if poi.category not in {"attraction", "food", "rest"}:
            raise RuntimeError(f"Invalid category {poi.category!r}")
        # Hybrid / agent compatibility
        if not poi.tags:
            raise RuntimeError(f"POI {poi.name!r} missing tags")
        if poi.cost_usd is None or poi.duration_minutes is None:
            raise RuntimeError(f"POI {poi.name!r} missing cost/duration for agent tools")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest real POIs from Overpass (+ optional Google Places)."
    )
    parser.add_argument(
        "--city",
        required=True,
        choices=sorted(CITY_REGISTRY.keys()),
        help="Target city key (tokyo, london, seoul).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max POIs to keep after extraction (default 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + validate only; do not write Supabase/Qdrant or call Vertex.",
    )
    parser.add_argument(
        "--skip-places",
        action="store_true",
        help="Skip Google Places enrichment even if GOOGLE_PLACES_API_KEY is set.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write extracted POI JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 1

    load_env()
    city_key = args.city.lower()
    meta = CITY_REGISTRY[city_key]

    print("GenAI Travel Compass — real POI ingest (Phase 5.1)")
    print(f"City: {meta['display_name']} ({city_key})")
    print(f"Limit: {args.limit}  dry_run={args.dry_run}")

    city_id: str | None = None
    safety_score = 3
    supabase = None

    if not args.dry_run:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            print(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required "
                "(or use --dry-run).",
                file=sys.stderr,
            )
            return 1
        supabase = create_client(url, key)
        city_row = resolve_city_row(supabase, city_key)
        if not city_row:
            print(
                f"City {meta['iso']}/{meta['slug']} not found in Supabase. "
                "Seed destinations first (scripts/seed_db.py). "
                "London may be missing from seed_data — add a city row or use tokyo.",
                file=sys.stderr,
            )
            return 1
        city_id = str(city_row["id"])
        safety_score = int(city_row.get("safety_index") or 3)
        print(f"Resolved city_id={city_id} safety_score={safety_score}")
    else:
        print("Dry-run: skipping Supabase city resolve (safety_score=3 default).")

    print("\n[1/4] Overpass extract…")
    try:
        elements = fetch_overpass_elements(city_key, limit=args.limit)
    except httpx.HTTPError as exc:
        print(f"Overpass request failed: {exc}", file=sys.stderr)
        return 1
    print(f"  raw elements: {len(elements)}")

    overpass_pois = elements_to_pois(
        elements,
        city_key=city_key,
        limit=args.limit,
        city_id=city_id,
        safety_score=safety_score,
    )
    print(f"  mapped Overpass POIs: {len(overpass_pois)}")

    from src.services.signature_pois import (
        build_signature_pois,
        merge_signature_and_overpass,
    )

    signature_city_id = city_id or str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dry-run-signature:{city_key}")
    )
    signatures = build_signature_pois(
        city_slug=city_key,
        city_id=signature_city_id,
        city_display=str(meta["display_name"]),
        safety_score=safety_score,
    )
    pois = merge_signature_and_overpass(signatures, overpass_pois)
    if len(pois) > args.limit:
        sigs = [p for p in pois if p.source == "signature"]
        rest = [p for p in pois if p.source != "signature"]
        room = max(0, args.limit - len(sigs))
        pois = [*sigs, *rest[:room]]
    print(f"  after signature merge: {len(pois)} (signatures={len(signatures)})")

    places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if places_key and not args.skip_places and not args.dry_run:
        print("\n[2/4] Google Places enrichment…")
        pois = enrich_with_places(pois, api_key=places_key)
    elif places_key and not args.skip_places and args.dry_run:
        print("\n[2/4] Places enrichment skipped in --dry-run (set without dry-run to enable).")
    else:
        print("\n[2/4] Places enrichment skipped (no GOOGLE_PLACES_API_KEY or --skip-places).")

    print("\n[3/4] Schema validation…")
    try:
        validate_structural(pois)
    except RuntimeError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"  OK — {len(pois)} POIs compatible with Phase 5.1 schema")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps([p.model_dump() for p in pois], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  wrote {args.json_out}")

    # Preview sample
    for sample in pois[:3]:
        print(
            f"  · {sample.name} [{sample.category}] "
            f"lat={sample.lat} lon={sample.lon} tags={sample.tags}"
        )

    if args.dry_run:
        print("\n[4/4] Dry-run complete — no Supabase / Qdrant writes.")
        print(
            "Structural check passed for Hybrid Search / agent fields "
            "(category in attraction|food|rest, tags, cost_usd, duration_minutes)."
        )
        return 0

    assert supabase is not None
    print("\n[4/4] Upsert Supabase + embed + Qdrant…")
    try:
        n_db = upsert_supabase_pois(supabase, pois)
        print(f"  Supabase upserted: {n_db}")
    except Exception as exc:  # noqa: BLE001
        print(
            f"Supabase upsert failed: {exc}\n"
            "Apply scripts/migrate_add_pois.sql in the SQL editor first.",
            file=sys.stderr,
        )
        return 1

    try:
        dims = embedding_dimensions()
        print(f"  Embedding {len(pois)} docs (text-embedding-004, {dims}-d)…")
        n_vec = upsert_qdrant_pois(pois)
        print(f"  Qdrant upserted: {n_vec} → collection travel_pois")
    except (EmbeddingServiceError, QdrantServiceError) as exc:
        print(f"Vector ingest failed: {exc}", file=sys.stderr)
        return 1

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "enrich_poi_photos", ROOT_DIR / "scripts" / "enrich_poi_photos.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load enrich_poi_photos")
        enrich_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(enrich_mod)
        enrich_mod.after_ingest_photos_and_cuisine(
            supabase,
            city_slug=city_key,
            city_id=str(city_id),
            city_display=str(meta["display_name"]),
            safety_score=safety_score,
            skip_places=bool(args.skip_places),
            upsert_qdrant=upsert_qdrant_pois,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: cuisine/photo enrich skipped ({exc})")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
