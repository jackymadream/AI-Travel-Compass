#!/usr/bin/env python3
"""
Patch photo_url on existing POIs (requires migrate_poi_photo_url.sql first).

Uses city/iso-aware Unsplash map from data/poi_category_photos.json.

If the column is missing, prints instructions and exits 0 — runtime search
already fills category stock photos without the column.

Usage:
  # Apply scripts/migrate_poi_photo_url.sql in Supabase SQL editor, then:
  python scripts/patch_poi_photos.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.services.itinerary_i18n import category_photo  # noqa: E402


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required", file=sys.stderr)
        return 1

    from postgrest.exceptions import APIError
    from supabase import create_client

    sb = create_client(url, key)
    try:
        sb.table("pois").select("id, photo_url").limit(1).execute()
    except APIError as exc:
        print(
            "pois.photo_url missing. Apply scripts/migrate_poi_photo_url.sql "
            f"in the Supabase SQL editor first. ({exc.message})"
        )
        print(
            "Runtime itinerary cards still show category stock photos via "
            "search_pois fallback — no action required for UI."
        )
        return 0

    # city_id → display name / slug for photo map keys
    city_name_by_id: dict[str, str] = {}
    try:
        city_rows = (
            sb.table("cities").select("id, name, slug").limit(500).execute().data or []
        )
        for c in city_rows:
            cid = str(c.get("id") or "")
            name = c.get("name")
            if isinstance(name, dict):
                display = str(name.get("en") or c.get("slug") or "")
            else:
                display = str(name or c.get("slug") or "")
            if cid and display:
                city_name_by_id[cid] = display
    except Exception as exc:  # noqa: BLE001
        print(f"warn: could not load cities for photo map ({exc})")

    page = 0
    page_size = 200
    updated = 0
    while True:
        start = page * page_size
        end = start + page_size - 1
        rows = (
            sb.table("pois")
            .select("id, city_id, name, category, photo_url")
            .range(start, end)
            .execute()
            .data
            or []
        )
        if not rows:
            break
        for i, row in enumerate(rows):
            if row.get("photo_url"):
                continue
            cat = str(row.get("category") or "attraction")
            city = city_name_by_id.get(str(row.get("city_id") or ""), "")
            sb.table("pois").update(
                {
                    "photo_url": category_photo(
                        cat,
                        index=start + i,
                        city=city or None,
                        poi_name=str(row.get("name") or ""),
                    )
                }
            ).eq("id", row["id"]).execute()
            updated += 1
        if len(rows) < page_size:
            break
        page += 1
        print(f"  scanned page {page}, updated so far {updated}")

    print(f"Done. Updated photo_url on {updated} POIs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
