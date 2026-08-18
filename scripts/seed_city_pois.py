#!/usr/bin/env python3
"""
Ensure every phase-6 city has enough POIs for the itinerary agent.

For each city in data/countries_phase6.json:
  1. Resolve cities.id in Supabase (iso + slug).
  2. Fetch Overpass POIs by default (use ``--synthetic-only`` to skip).
  3. Delete existing ``source=synthetic`` rows for the city so generics do not
     keep winning retrieval.
  4. Backfill synthetic attraction/food/rest POIs only when category counts
     fall below thresholds.
  5. Upsert Supabase ``pois`` + embed into Qdrant ``travel_pois``.

Usage
-----
  python scripts/seed_city_pois.py --all --skip-places --limit 60
  python scripts/seed_city_pois.py --city osaka --skip-places --limit 60
  python scripts/seed_city_pois.py --all --synthetic-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import importlib.util

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _load_ingest_module() -> Any:
    path = ROOT_DIR / "scripts" / "ingest_real_pois.py"
    spec = importlib.util.spec_from_file_location("ingest_real_pois", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ingest = _load_ingest_module()
CITY_REGISTRY = _ingest.CITY_REGISTRY
elements_to_pois = _ingest.elements_to_pois
enrich_with_places = _ingest.enrich_with_places
fetch_overpass_elements = _ingest.fetch_overpass_elements
resolve_city_row = _ingest.resolve_city_row
upsert_qdrant_pois = _ingest.upsert_qdrant_pois
upsert_supabase_pois = _ingest.upsert_supabase_pois
validate_structural = _ingest.validate_structural

from src.schemas.poi import PoiRecord  # noqa: E402
from src.services.itinerary_i18n import category_photo  # noqa: E402

PHASE6_PATH = ROOT_DIR / "data" / "countries_phase6.json"
BBOX_DELTA = 0.12

MIN_ATTRACTION = 6
MIN_FOOD = 4
MIN_REST = 2
MIN_NIGHTLIFE = 8
MIN_POPULAR = 12

SYNTHETIC_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "attraction": [
        {
            "suffix": "Historic District Walk",
            "tags": ["attraction", "culture", "history", "sightseeing"],
            "cost": 0,
            "duration": 90,
            "desc": "Walk the historic core and signature landmarks.",
        },
        {
            "suffix": "City Museum",
            "tags": ["attraction", "museum", "culture"],
            "cost": 12,
            "duration": 120,
            "desc": "Local history and culture museum highlight.",
        },
        {
            "suffix": "Viewpoint Terrace",
            "tags": ["attraction", "viewpoint", "photo"],
            "cost": 8,
            "duration": 60,
            "desc": "Elevated viewpoint for skyline and photo stops.",
        },
        {
            "suffix": "Market Quarter",
            "tags": ["attraction", "market", "urban"],
            "cost": 0,
            "duration": 75,
            "desc": "Bustling market streets and local craft stalls.",
        },
        {
            "suffix": "Architecture Trail",
            "tags": ["attraction", "architecture", "urban"],
            "cost": 0,
            "duration": 90,
            "desc": "Signature buildings and neighborhood architecture.",
        },
        {
            "suffix": "Cultural Landmark",
            "tags": ["attraction", "culture", "temple"],
            "cost": 5,
            "duration": 75,
            "desc": "Iconic cultural or religious landmark visit.",
        },
        {
            "suffix": "Waterfront Promenade",
            "tags": ["attraction", "scenic", "photo"],
            "cost": 0,
            "duration": 60,
            "desc": "Riverside or seaside promenade stroll.",
        },
        {
            "suffix": "Neighborhood Discovery",
            "tags": ["attraction", "urban", "nightlife"],
            "cost": 0,
            "duration": 90,
            "desc": "Explore a characterful local neighborhood.",
        },
    ],
    "food": [
        {
            "suffix": "Street Food Lane",
            "tags": ["food", "street-food"],
            "cost": 12,
            "duration": 60,
            "desc": "Casual street-food tasting stretch.",
        },
        {
            "suffix": "Local Bistro District",
            "tags": ["food", "restaurant"],
            "cost": 22,
            "duration": 75,
            "desc": "Neighborhood bistros and regional cooking.",
        },
        {
            "suffix": "Cafe Culture Spot",
            "tags": ["food", "cafe"],
            "cost": 10,
            "duration": 45,
            "desc": "Signature cafe stop for a lighter bite.",
        },
        {
            "suffix": "Night Market Bites",
            "tags": ["food", "market", "nightlife"],
            "cost": 15,
            "duration": 60,
            "desc": "Evening food stalls and local snacks.",
        },
        {
            "suffix": "Regional Cuisine Hall",
            "tags": ["food", "restaurant"],
            "cost": 28,
            "duration": 90,
            "desc": "Regional specialty dining area.",
        },
        {
            "suffix": "Seafood Counter Row",
            "tags": ["food", "seafood"],
            "cost": 25,
            "duration": 75,
            "desc": "Fresh seafood counters and casual plates.",
        },
    ],
    "rest": [
        {
            "suffix": "Central Park Pause",
            "tags": ["rest", "park"],
            "cost": 0,
            "duration": 60,
            "desc": "Green park break between sightseeing stops.",
        },
        {
            "suffix": "Garden Retreat",
            "tags": ["rest", "garden"],
            "cost": 5,
            "duration": 60,
            "desc": "Quiet garden for a slower mid-day reset.",
        },
        {
            "suffix": "Wellness Spa Stop",
            "tags": ["rest", "wellness"],
            "cost": 30,
            "duration": 90,
            "desc": "Spa or bath house to recover travel pace.",
        },
        {
            "suffix": "Riverside Rest",
            "tags": ["rest", "park", "scenic"],
            "cost": 0,
            "duration": 45,
            "desc": "Calm riverside or lakeside rest area.",
        },
    ],
}

NIGHTLIFE_TEMPLATES: list[dict[str, Any]] = [
    {
        "suffix": "Laneway Bar Crawl",
        "category": "food",
        "tags": ["food", "nightlife", "bar"],
        "cost": 20,
        "duration": 75,
        "desc": "Compact alley bars and late-night drinks.",
    },
    {
        "suffix": "Jazz Club Evening",
        "category": "attraction",
        "tags": ["attraction", "nightlife", "music"],
        "cost": 28,
        "duration": 90,
        "desc": "Live-music nightlife stop after dinner.",
    },
    {
        "suffix": "Night Market Lights",
        "category": "attraction",
        "tags": ["attraction", "nightlife", "market"],
        "cost": 0,
        "duration": 75,
        "desc": "Evening market streets and neon neighborhoods.",
    },
    {
        "suffix": "Rooftop Cocktail Terrace",
        "category": "food",
        "tags": ["food", "nightlife", "bar"],
        "cost": 24,
        "duration": 60,
        "desc": "Skyline drinks with a later start time.",
    },
]

POPULAR_TEMPLATES: list[dict[str, Any]] = [
    {
        "suffix": "Iconic Landmark Circuit",
        "category": "attraction",
        "tags": ["attraction", "popular", "sightseeing", "wikipedia"],
        "cost": 0,
        "duration": 90,
        "desc": "The city's best-known landmark walking loop.",
    },
    {
        "suffix": "Flagship Museum",
        "category": "attraction",
        "tags": ["attraction", "popular", "museum", "wikipedia"],
        "cost": 15,
        "duration": 120,
        "desc": "Headline museum most first-time visitors book.",
    },
    {
        "suffix": "Observation Deck",
        "category": "attraction",
        "tags": ["attraction", "popular", "viewpoint", "wikipedia"],
        "cost": 20,
        "duration": 75,
        "desc": "Popular observation deck with city views.",
    },
]


def load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def load_phase6_cities() -> list[dict[str, Any]]:
    payload = json.loads(PHASE6_PATH.read_text(encoding="utf-8"))
    countries = payload.get("countries") or payload
    if isinstance(countries, dict):
        countries = list(countries.values())
    out: list[dict[str, Any]] = []
    for country in countries:
        iso = str(country.get("iso_code") or country.get("iso") or "").upper()
        for city in country.get("cities") or []:
            lat = city.get("latitude")
            lon = city.get("longitude")
            if lat is None or lon is None:
                continue
            name = city.get("name") or {}
            display = (
                name.get("en")
                if isinstance(name, dict)
                else str(name or city.get("slug"))
            )
            out.append(
                {
                    "slug": str(city["slug"]),
                    "iso": iso,
                    "display_name": str(display),
                    "lat": float(lat),
                    "lon": float(lon),
                    "safety_index": int(city.get("safety_index") or 3),
                    "tags": list(city.get("tags") or []),
                    "bbox": (
                        float(lat) - BBOX_DELTA,
                        float(lon) - BBOX_DELTA,
                        float(lat) + BBOX_DELTA,
                        float(lon) + BBOX_DELTA,
                    ),
                }
            )
    return out


def register_cities(cities: list[dict[str, Any]]) -> None:
    """Merge phase6 cities into ingest CITY_REGISTRY (mutates module dict)."""
    for city in cities:
        key = city["slug"]
        CITY_REGISTRY[key] = {
            "slug": city["slug"],
            "iso": city["iso"],
            "display_name": city["display_name"],
            "bbox": city["bbox"],
            "lat": city["lat"],
            "lon": city["lon"],
        }


def poi_id_synthetic(city_id: str, category: str, index: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"travel-compass:poi:synthetic:{city_id}:{category}:{index}",
        )
    )


def count_by_tag(pois: list[PoiRecord], tag: str) -> int:
    needle = tag.lower()
    return sum(
        1
        for p in pois
        if any(needle == str(t).lower() or needle in str(t).lower() for t in p.tags)
    )


def count_by_category(pois: list[PoiRecord]) -> dict[str, int]:
    counts = {"attraction": 0, "food": 0, "rest": 0}
    for p in pois:
        if p.category in counts:
            counts[p.category] += 1
    return counts


def _synthetic_record(
    *,
    city: dict[str, Any],
    city_id: str,
    display: str,
    safety: int,
    tmpl: dict[str, Any],
    index: int,
    key: str,
) -> PoiRecord:
    lat0 = float(city["lat"])
    lon0 = float(city["lon"])
    city_tags = [str(t) for t in city.get("tags") or []]
    jitter_lat = ((index % 5) - 2) * 0.008
    jitter_lon = ((index // 5) % 5 - 2) * 0.008
    category = str(tmpl.get("category") or "attraction")
    name = f"{display} {tmpl['suffix']}" if index == 0 else f"{display} {tmpl['suffix']} {index + 1}"
    tags = list(dict.fromkeys([*tmpl["tags"], *city_tags[:4]]))
    return PoiRecord(
        id=poi_id_synthetic(city_id, key, index),
        name=name,
        city=display,
        category=category,  # type: ignore[arg-type]
        description=f"{tmpl['desc']} ({display})",
        lat=lat0 + jitter_lat,
        lon=lon0 + jitter_lon,
        price_level=0 if tmpl["cost"] <= 0 else (1 if tmpl["cost"] < 20 else 2),
        rating=4.3,
        safety_score=safety,
        city_id=city_id,
        tags=tags,
        cost_usd=float(tmpl["cost"]),
        duration_minutes=int(tmpl["duration"]),
        address=f"Central {display}",
        photo_url=category_photo(
            category,
            index,
            city=display,
            iso=str(city.get("iso") or "").lower() or None,
            poi_name=name,
        ),
        source="synthetic",
    )


def build_synthetic_pois(
    *,
    city: dict[str, Any],
    city_id: str,
    existing: list[PoiRecord],
) -> list[PoiRecord]:
    counts = count_by_category(existing)
    targets = {
        "attraction": MIN_ATTRACTION,
        "food": MIN_FOOD,
        "rest": MIN_REST,
    }
    display = city["display_name"]
    safety = int(city.get("safety_index") or 3)
    extras: list[PoiRecord] = []

    for category, need in targets.items():
        have = counts.get(category, 0)
        templates = SYNTHETIC_TEMPLATES[category]
        index = 0
        while have + len([p for p in extras if p.category == category]) < need:
            tmpl = dict(templates[index % len(templates)])
            tmpl["category"] = category
            extras.append(
                _synthetic_record(
                    city=city,
                    city_id=city_id,
                    display=display,
                    safety=safety,
                    tmpl=tmpl,
                    index=index,
                    key=category,
                )
            )
            index += 1
            if index > 40:
                break

    combined = [*existing, *extras]
    nightlife_have = count_by_tag(combined, "nightlife")
    night_index = 0
    while nightlife_have < MIN_NIGHTLIFE:
        tmpl = NIGHTLIFE_TEMPLATES[night_index % len(NIGHTLIFE_TEMPLATES)]
        extras.append(
            _synthetic_record(
                city=city,
                city_id=city_id,
                display=display,
                safety=safety,
                tmpl=tmpl,
                index=night_index,
                key="nightlife",
            )
        )
        nightlife_have += 1
        night_index += 1
        if night_index > 40:
            break

    combined = [*existing, *extras]
    popular_have = count_by_tag(combined, "popular")
    pop_index = 0
    while popular_have < MIN_POPULAR:
        tmpl = POPULAR_TEMPLATES[pop_index % len(POPULAR_TEMPLATES)]
        extras.append(
            _synthetic_record(
                city=city,
                city_id=city_id,
                display=display,
                safety=safety,
                tmpl=tmpl,
                index=pop_index,
                key="popular",
            )
        )
        popular_have += 1
        pop_index += 1
        if pop_index > 40:
            break
    return extras


def delete_synthetic_pois(supabase: Any, city_id: str) -> int:
    """Remove generic synthetic rows so Overpass names win retrieval."""
    try:
        existing = (
            supabase.table("pois")
            .select("id")
            .eq("city_id", city_id)
            .eq("source", "synthetic")
            .execute()
        )
        ids = [str(r["id"]) for r in (existing.data or []) if r.get("id")]
        if not ids:
            return 0
        supabase.table("pois").delete().eq("city_id", city_id).eq(
            "source", "synthetic"
        ).execute()
        try:
            from src.services.qdrant_service import delete_poi_vectors

            delete_poi_vectors(ids)
        except Exception as exc:  # noqa: BLE001
            print(f"  warn: qdrant synthetic cleanup skipped ({exc})")
        return len(ids)
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: could not delete synthetic POIs ({exc})")
        return 0


def delete_overpass_pois(supabase: Any, city_id: str) -> int:
    """Drop prior Overpass rows so neighborhood churches do not linger after a re-seed."""
    try:
        existing = (
            supabase.table("pois")
            .select("id")
            .eq("city_id", city_id)
            .in_("source", ["overpass", "overpass+places"])
            .execute()
        )
        ids = [str(r["id"]) for r in (existing.data or []) if r.get("id")]
        if not ids:
            return 0
        supabase.table("pois").delete().eq("city_id", city_id).in_(
            "source", ["overpass", "overpass+places"]
        ).execute()
        try:
            from src.services.qdrant_service import delete_poi_vectors

            delete_poi_vectors(ids)
        except Exception as exc:  # noqa: BLE001
            print(f"  warn: qdrant overpass cleanup skipped ({exc})")
        return len(ids)
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: could not delete overpass POIs ({exc})")
        return 0


def attach_fallback_photos(pois: list[PoiRecord], *, iso: str) -> None:
    for i, poi in enumerate(pois):
        if poi.photo_url:
            continue
        poi.photo_url = category_photo(
            poi.category,
            i,
            city=poi.city,
            iso=iso.lower() or None,
            poi_name=poi.name,
        )


def ingest_city(
    city: dict[str, Any],
    *,
    supabase: Any,
    limit: int,
    try_overpass: bool,
    skip_places: bool,
    dry_run: bool,
    replace_synthetic: bool,
) -> int:
    city_key = city["slug"]
    city_row = resolve_city_row(supabase, city_key) if not dry_run else None
    if not dry_run and not city_row:
        print(f"  skip {city_key}: not found in Supabase (seed countries first)")
        return 0

    city_id = str(city_row["id"]) if city_row else str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dry-run:{city['iso']}:{city_key}")
    )
    safety = int(
        (city_row or {}).get("safety_index")
        or city.get("safety_index")
        or 3
    )

    if replace_synthetic and not dry_run and supabase is not None:
        n_del = delete_synthetic_pois(supabase, city_id)
        if n_del:
            print(f"  removed synthetic: {n_del}")

    pois: list[PoiRecord] = []
    if try_overpass:
        try:
            elements = fetch_overpass_elements(city_key, limit=limit)
            pois = elements_to_pois(
                elements,
                city_key=city_key,
                limit=limit,
                city_id=city_id,
                safety_score=safety,
            )
            print(f"  overpass mapped: {len(pois)}")
            if not dry_run and supabase is not None and pois:
                n_old = delete_overpass_pois(supabase, city_id)
                if n_old:
                    print(f"  removed prior overpass: {n_old}")
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            print(f"  overpass failed ({exc}); continuing with synthetic")

    synthetic = build_synthetic_pois(city=city, city_id=city_id, existing=pois)
    if synthetic:
        print(f"  synthetic backfill: +{len(synthetic)}")
        pois = [*pois, *synthetic]

    # Cap total while keeping category balance — prefer Overpass over synthetic.
    if len(pois) > limit:
        real = [p for p in pois if p.source != "synthetic"]
        synth = [p for p in pois if p.source == "synthetic"]
        pois = [*real[:limit], *synth][:limit]

    places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if places_key and not skip_places and not dry_run and try_overpass:
        pois = enrich_with_places(pois, api_key=places_key)

    attach_fallback_photos(pois, iso=str(city.get("iso") or ""))

    if not pois:
        print(f"  no POIs for {city_key}")
        return 0

    validate_structural(pois)
    if dry_run:
        print(f"  dry-run OK ({len(pois)} POIs)")
        return len(pois)

    n_db = upsert_supabase_pois(supabase, pois)
    n_vec = upsert_qdrant_pois(pois)
    print(f"  upserted supabase={n_db} qdrant={n_vec}")
    return len(pois)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed POIs for phase-6 cities.")
    p.add_argument("--all", action="store_true", help="Process every phase-6 city.")
    p.add_argument("--city", type=str, default=None, help="Single city slug.")
    p.add_argument("--limit", type=int, default=60, help="Max POIs per city.")
    p.add_argument(
        "--try-overpass",
        action="store_true",
        default=True,
        help="Attempt Overpass before synthetic backfill (default on).",
    )
    p.add_argument(
        "--no-overpass",
        action="store_true",
        help="Skip Overpass (alias of --synthetic-only).",
    )
    p.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Skip Overpass; synthetic templates only.",
    )
    p.add_argument(
        "--keep-synthetic",
        action="store_true",
        help="Do not delete existing source=synthetic rows before upsert.",
    )
    p.add_argument("--skip-places", action="store_true", default=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.all and not args.city:
        print("Provide --all or --city <slug>", file=sys.stderr)
        return 1

    load_env()
    cities = load_phase6_cities()
    register_cities(cities)

    if args.city:
        selected = [c for c in cities if c["slug"] == args.city.lower()]
        if not selected:
            print(f"Unknown city slug: {args.city}", file=sys.stderr)
            return 1
    else:
        # Prefer JP cities first for operator runs of --all.
        jp_first = [c for c in cities if c["iso"] == "JP"]
        rest = [c for c in cities if c["iso"] != "JP"]
        selected = [*jp_first, *rest]

    try_overpass = not (bool(args.synthetic_only) or bool(args.no_overpass))
    replace_synthetic = not bool(args.keep_synthetic)

    supabase = None
    if not args.dry_run:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required", file=sys.stderr)
            return 1
        supabase = create_client(url, key)

    print(
        f"Seeding POIs for {len(selected)} city(ies) "
        f"(overpass={try_overpass}, replace_synthetic={replace_synthetic}, "
        f"dry_run={args.dry_run})"
    )
    total = 0
    for i, city in enumerate(selected, start=1):
        print(f"[{i}/{len(selected)}] {city['display_name']} ({city['slug']})")
        total += ingest_city(
            city,
            supabase=supabase,
            limit=max(12, args.limit),
            try_overpass=try_overpass,
            skip_places=args.skip_places,
            dry_run=args.dry_run,
            replace_synthetic=replace_synthetic,
        )
    print(f"Done. Seeded ~{total} POI records across runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
