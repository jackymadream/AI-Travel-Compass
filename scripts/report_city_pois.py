#!/usr/bin/env python3
"""
Report POI corpus diversity for a city (Tokyo pilot / any slug).

Usage::

    python scripts/report_city_pois.py --city tokyo
    python scripts/report_city_pois.py --city tokyo --json-out .scratch/tokyo_pois.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.signature_pois import (  # noqa: E402
    build_signature_pois,
    signature_entries_for_city,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize POI diversity for a city slug.")
    p.add_argument("--city", required=True, help="City slug (e.g. tokyo).")
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write full report JSON.",
    )
    p.add_argument(
        "--signatures-only",
        action="store_true",
        help="Skip Supabase; report curated signature file only.",
    )
    return p.parse_args()


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_source = Counter(str(r.get("source") or "unknown") for r in rows)
    by_category = Counter(str(r.get("category") or "unknown") for r in rows)
    tag_hist: Counter[str] = Counter()
    neighborhoods: Counter[str] = Counter()
    for row in rows:
        for tag in row.get("tags") or []:
            t = str(tag).lower()
            if t.startswith("neighborhood:"):
                neighborhoods[t.split(":", 1)[-1]] += 1
            elif t.startswith("wikidata:") or t.startswith("name_en:"):
                continue
            else:
                tag_hist[t] += 1
    samples: dict[str, list[str]] = {"attraction": [], "food": [], "rest": []}
    for row in rows:
        cat = str(row.get("category") or "")
        if cat in samples and len(samples[cat]) < 8:
            samples[cat].append(str(row.get("name") or ""))
    return {
        "total": len(rows),
        "by_source": dict(by_source),
        "by_category": dict(by_category),
        "top_tags": tag_hist.most_common(25),
        "neighborhoods": dict(neighborhoods.most_common(20)),
        "samples": samples,
    }


def fetch_supabase_pois(city_slug: str) -> list[dict[str, Any]]:
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    client = create_client(url, key)
    countries = client.table("countries").select("id, iso_code").execute().data or []
    cities = (
        client.table("cities")
        .select("id, slug, country_id, name")
        .eq("slug", city_slug.lower())
        .execute()
        .data
        or []
    )
    if not cities:
        raise RuntimeError(f"No city with slug={city_slug!r}")
    city_id = str(cities[0]["id"])
    rows = (
        client.table("pois")
        .select("id, name, category, tags, source, latitude, longitude")
        .eq("city_id", city_id)
        .eq("is_active", True)
        .limit(2000)
        .execute()
        .data
        or []
    )
    return rows


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    slug = args.city.lower()

    sig_entries = signature_entries_for_city(slug)
    print(f"City slug: {slug}")
    print(f"Signature file entries: {len(sig_entries)}")
    sig_summary: dict[str, Any] | None = None
    if sig_entries:
        sig_pois = build_signature_pois(
            city_slug=slug,
            city_id="00000000-0000-0000-0000-000000000000",
            city_display=slug.title(),
        )
        sig_summary = summarize_rows([p.model_dump() for p in sig_pois])
        print("\n=== Curated signatures ===")
        print(json.dumps(sig_summary, indent=2, ensure_ascii=False))

    report: dict[str, Any] = {
        "city": slug,
        "signature_file_count": len(sig_entries),
        "signatures": sig_summary,
    }

    if not args.signatures_only:
        try:
            rows = fetch_supabase_pois(slug)
            live = summarize_rows(rows)
            report["supabase"] = live
            print("\n=== Supabase live POIs ===")
            print(json.dumps(live, indent=2, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(f"\nSupabase report skipped: {exc}", file=sys.stderr)
            report["supabase_error"] = str(exc)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
