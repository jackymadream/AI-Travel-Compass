#!/usr/bin/env python3
"""
Resolve and persist POI photos after Overpass ingest.

Priority (fail-closed): Wikidata P18+P625 → Wikipedia title+geo → Places photos.
Cuisine catalog rows keep seeded photos. Attractions/rest without a grounded
hit get photo_source=none (UI placeholder), never a generic Unsplash postcard.

Usage
-----
  python scripts/enrich_poi_photos.py --city kyoto
  python scripts/enrich_poi_photos.py --city-id <uuid> --force
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.services.poi_photos import (  # noqa: E402
    PhotoHit,
    persistable_photo_url,
    resolve_grounded_photo,
    resolve_places_photo,
)
from src.schemas.poi import PoiRecord  # noqa: E402
from src.services.cache_service import invalidate_poi_cache  # noqa: E402

FRESH_DAYS = 14
PAGE_SIZE = 200


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _wikidata_qid(tags: list[Any], wikidata: str | None = None) -> str | None:
    if wikidata and str(wikidata).strip():
        return str(wikidata).strip()
    for tag in tags or []:
        raw = str(tag)
        if raw.lower().startswith("wikidata:"):
            return raw.split(":", 1)[1].strip() or None
    return None


def enrich_row(
    row: dict[str, Any],
    *,
    places_key: str,
    skip_places: bool,
) -> PhotoHit:
    source = str(row.get("source") or "")
    if source == "cuisine_catalog":
        # Meal stock photos disabled — keep empty; UI uses lunch/dinner icons.
        # Do not resolve Wikidata/Places for cuisine_catalog rows.
        url = persistable_photo_url(str(row.get("photo_url") or "") or None)
        return PhotoHit(
            url=url,
            source="cuisine_seed" if url else "none",
            confidence="high" if url else "low",
            google_place_name=str(row.get("google_place_name") or "") or None,
            google_photo_name=str(row.get("google_photo_name") or "") or None,
        )
    name = str(row.get("name") or "")
    city = str(row.get("city") or "")
    lat = _as_float(row.get("latitude") if row.get("latitude") is not None else row.get("lat"))
    lon = _as_float(row.get("longitude") if row.get("longitude") is not None else row.get("lon"))
    tags = row.get("tags") or []
    qid = _wikidata_qid(tags if isinstance(tags, list) else [])
    hit = resolve_grounded_photo(
        name,
        city=city or None,
        wikidata=qid,
        lat=lat,
        lon=lon,
        tags=tags if isinstance(tags, list) else [],
    )
    if hit.url:
        return hit
    if skip_places or not places_key:
        return PhotoHit(url=None, source="none", confidence="low")
    return resolve_places_photo(
        name,
        city=city or None,
        lat=lat,
        lon=lon,
        api_key=places_key,
        google_place_name=str(row.get("google_place_name") or "") or None,
        google_photo_name=str(row.get("google_photo_name") or "") or None,
    )


def load_rows(supabase: Any, *, city_id: str | None, city_slug: str | None) -> list[dict[str, Any]]:
    city_display = ""
    if city_id:
        try:
            crow = (
                supabase.table("cities")
                .select("name, slug")
                .eq("id", city_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if crow:
                name = crow[0].get("name")
                if isinstance(name, dict):
                    city_display = str(name.get("en") or crow[0].get("slug") or "")
                else:
                    city_display = str(name or crow[0].get("slug") or "")
        except Exception:  # noqa: BLE001
            city_display = city_slug or ""
    query = (
        supabase.table("pois")
        .select(
            "id, city_id, name, category, description, tags, source, latitude, longitude, "
            "price_level, rating, safety_score, cost_usd, duration_minutes, "
            "user_ratings_total, places_primary_type, address, photo_url, "
            "photo_source, photo_confidence, photo_checked_at, "
            "google_place_name, google_photo_name"
        )
        .eq("is_active", True)
    )
    if city_id:
        query = query.eq("city_id", city_id)
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        chunk = query.range(start, start + PAGE_SIZE - 1).execute()
        data = chunk.data or []
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    if city_slug and not city_id:
        cities = (
            supabase.table("cities")
            .select("id, slug, name")
            .eq("slug", city_slug)
            .limit(5)
            .execute()
            .data
            or []
        )
        ids = {str(c["id"]) for c in cities if c.get("id")}
        rows = [r for r in rows if str(r.get("city_id") or "") in ids]
        if not city_display and cities:
            name = cities[0].get("name")
            if isinstance(name, dict):
                city_display = str(name.get("en") or city_slug or "")
            else:
                city_display = str(name or city_slug or "")
    for row in rows:
        row.setdefault("city", city_display)
    return rows


def is_fresh(row: dict[str, Any], *, force: bool) -> bool:
    if force:
        return False
    raw = row.get("photo_checked_at")
    if not raw:
        return False
    try:
        checked = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - checked < timedelta(days=FRESH_DAYS)


def apply_hit(supabase: Any, row_id: str, hit: PhotoHit) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("pois").update(
        {
            "photo_url": hit.url,
            "photo_source": hit.source,
            "photo_confidence": hit.confidence,
            "photo_checked_at": now,
            "google_place_name": hit.google_place_name,
            "google_photo_name": hit.google_photo_name,
        }
    ).eq("id", row_id).execute()


def poi_record_with_hit(row: dict[str, Any], hit: PhotoHit) -> PoiRecord:
    return PoiRecord(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or ""),
        city=str(row.get("city") or ""),
        category=str(row.get("category") or "attraction"),  # type: ignore[arg-type]
        description=str(row.get("description") or row.get("name") or ""),
        lat=_as_float(row.get("latitude") if row.get("latitude") is not None else row.get("lat")),
        lon=_as_float(row.get("longitude") if row.get("longitude") is not None else row.get("lon")),
        price_level=int(row["price_level"]) if row.get("price_level") is not None else None,
        rating=float(row["rating"]) if row.get("rating") is not None else None,
        safety_score=int(row.get("safety_score") or 3),
        city_id=str(row.get("city_id") or "") or None,
        tags=[str(tag) for tag in (row.get("tags") or [])],
        cost_usd=float(row["cost_usd"]) if row.get("cost_usd") is not None else None,
        duration_minutes=int(row["duration_minutes"]) if row.get("duration_minutes") is not None else None,
        user_ratings_total=int(row["user_ratings_total"]) if row.get("user_ratings_total") is not None else None,
        primary_type=str(row.get("places_primary_type") or row.get("primary_type") or "") or None,
        address=str(row.get("address") or "") or None,
        photo_url=hit.url,
        photo_source=hit.source,
        photo_confidence=hit.confidence,
        photo_checked_at=str(row.get("photo_checked_at") or "") or None,
        google_place_name=hit.google_place_name,
        google_photo_name=hit.google_photo_name,
        source=str(row.get("source") or "overpass"),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Persist grounded POI photos.")
    p.add_argument("--city", type=str, default=None, help="City slug (kyoto, tokyo, …).")
    p.add_argument("--city-id", type=str, default=None, help="cities.id UUID.")
    p.add_argument("--force", action="store_true", help="Re-check rows with a fresh photo_checked_at.")
    p.add_argument("--skip-places", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max rows to enrich (0 = all).")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def after_ingest_photos_and_cuisine(
    supabase: Any,
    *,
    city_slug: str,
    city_id: str,
    city_display: str,
    safety_score: int = 3,
    skip_places: bool = False,
    dry_run: bool = False,
    upsert_qdrant: Any | None = None,
) -> int:
    """Upsert cuisine catalog, embed it, then enrich all city POI photos."""
    from src.services.cuisine_catalog import upsert_cuisine_catalog

    if dry_run:
        print("  skip cuisine/photo persist (dry-run)")
        return 0
    records = upsert_cuisine_catalog(
        supabase,
        city_slug=city_slug,
        city_id=city_id,
        city_display=city_display,
        safety_score=safety_score,
    )
    print(f"  cuisine catalog: {len(records)} food-type POIs")
    if records and upsert_qdrant is not None:
        try:
            n_vec = upsert_qdrant(records)
            print(f"  cuisine qdrant: {n_vec}")
        except Exception as exc:  # noqa: BLE001
            print(f"  warn: cuisine embed/qdrant skipped ({exc})")
    return enrich_city_photos(
        supabase,
        city_id=city_id,
        city_slug=city_slug,
        skip_places=skip_places,
        city_display=city_display,
        upsert_qdrant=upsert_qdrant,
    )


def enrich_city_photos(
    supabase: Any,
    *,
    city_id: str | None = None,
    city_slug: str | None = None,
    force: bool = False,
    skip_places: bool = False,
    limit: int = 0,
    dry_run: bool = False,
    city_display: str | None = None,
    upsert_qdrant: Any | None = None,
) -> int:
    places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    rows = load_rows(supabase, city_id=city_id, city_slug=city_slug)
    resolved_city_id = city_id
    if not resolved_city_id:
        for row in rows:
            rid = str(row.get("city_id") or "").strip()
            if rid:
                resolved_city_id = rid
                break
    if city_display:
        for row in rows:
            row.setdefault("city", city_display)
    updated = 0
    skipped = 0
    refreshed: list[PoiRecord] = []
    for row in rows:
        if limit and updated >= limit:
            break
        if is_fresh(row, force=force):
            skipped += 1
            continue
        hit = enrich_row(row, places_key=places_key, skip_places=skip_places)
        rid = str(row.get("id") or "")
        if not rid:
            continue
        if dry_run:
            print(f"  dry {row.get('name')}: {hit.source} {hit.url or '(none)'}")
            updated += 1
            continue
        apply_hit(supabase, rid, hit)
        refreshed.append(poi_record_with_hit(row, hit))
        updated += 1
        time.sleep(0.05)
    if not dry_run and refreshed and upsert_qdrant is not None:
        try:
            n_vec = upsert_qdrant(refreshed)
            print(f"  photo qdrant refresh: {n_vec}")
        except Exception as exc:  # noqa: BLE001
            print(f"  warn: photo qdrant refresh skipped ({exc})")
    if not dry_run and resolved_city_id:
        n_cache = invalidate_poi_cache(resolved_city_id)
        print(f"  poi cache invalidated: {n_cache}")
    print(f"  photo enrich: updated={updated} skipped_fresh={skipped}")
    return updated


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT_DIR / ".env")
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required", file=sys.stderr)
        return 1
    if not args.city and not args.city_id:
        print("Provide --city or --city-id", file=sys.stderr)
        return 1
    from supabase import create_client
    from scripts.ingest_real_pois import upsert_qdrant_pois

    supabase = create_client(url, key)
    enrich_city_photos(
        supabase,
        city_id=args.city_id,
        city_slug=args.city.lower() if args.city else None,
        force=bool(args.force),
        skip_places=bool(args.skip_places),
        limit=int(args.limit or 0),
        dry_run=bool(args.dry_run),
        upsert_qdrant=upsert_qdrant_pois,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
