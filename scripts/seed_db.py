#!/usr/bin/env python3
"""
Seed Supabase PostgreSQL tables (countries, cities) from data/seed_data.json.

Environment setup
-----------------
1. Copy .env.example to .env in the project root:
     cp .env.example .env        # macOS / Linux
     copy .env.example .env      # Windows

2. Fill in credentials from Supabase Dashboard → Project Settings → API:
     SUPABASE_URL              Project URL  (https://<ref>.supabase.co)
     SUPABASE_SERVICE_ROLE_KEY Service role key (secret — never commit)

   Use the service role key (not the anon key) so inserts bypass RLS.

3. If your live DB was created before city tags existed, run once in SQL Editor:
     ALTER TABLE cities ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
     CREATE INDEX IF NOT EXISTS idx_cities_tags_gin ON cities USING GIN (tags);

4. Install dependencies:
     pip install -r requirements.txt

5. Run:
     python scripts/seed_db.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

ROOT_DIR = Path(__file__).resolve().parent.parent
SEED_FILE = ROOT_DIR / "data" / "seed_data.json"

REQUIRED_LOCALES = ("en", "zh-HK", "ja")
VALID_SEASONS = {"spring", "summer", "autumn", "winter"}

COUNTRY_COLUMNS = {
    "iso_code",
    "name",
    "description",
    "safety_index",
    "avg_daily_cost_usd",
    "best_travel_season",
    "region_tags",
}

CITY_COLUMNS = {
    "slug",
    "name",
    "description",
    "safety_index",
    "avg_daily_cost_usd",
    "best_travel_season",
    "latitude",
    "longitude",
    "tags",
}


def load_config() -> tuple[str, str]:
    load_dotenv(ROOT_DIR / ".env")

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    missing = [
        name
        for name, value in [
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_ROLE_KEY", key),
        ]
        if not value
    ]
    if missing:
        print(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\n\nCopy .env.example to .env and set values from "
            "Supabase Dashboard → Project Settings → API.",
            file=sys.stderr,
        )
        sys.exit(1)

    return url, key


def load_seed_data() -> dict[str, Any]:
    if not SEED_FILE.exists():
        print(f"Seed file not found: {SEED_FILE}", file=sys.stderr)
        sys.exit(1)

    with SEED_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def assert_i18n(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object with locales {REQUIRED_LOCALES}")
    for locale in REQUIRED_LOCALES:
        text = value.get(locale)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{path} missing non-empty '{locale}'")


def assert_best_travel_season(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    seasons = value.get("seasons")
    months = value.get("months")
    if not isinstance(seasons, list) or not seasons:
        raise ValueError(f"{path}.seasons must be a non-empty array")
    if any(season not in VALID_SEASONS for season in seasons):
        raise ValueError(f"{path}.seasons contains invalid values")
    if not isinstance(months, list) or not months:
        raise ValueError(f"{path}.months must be a non-empty array")
    if any(not isinstance(m, int) or m < 1 or m > 12 for m in months):
        raise ValueError(f"{path}.months must be integers 1–12")
    assert_i18n(value.get("label"), f"{path}.label")


def validate_seed(data: dict[str, Any]) -> None:
    countries = data.get("countries")
    if not isinstance(countries, list) or not countries:
        raise ValueError("seed_data.json must contain a non-empty 'countries' array")

    for i, country in enumerate(countries):
        prefix = f"countries[{i}]"
        for field in ("iso_code", "name", "description", "best_travel_season"):
            if field not in country:
                raise ValueError(f"{prefix} missing '{field}'")
        if len(country["iso_code"]) != 2:
            raise ValueError(f"{prefix}.iso_code must be a 2-letter code")
        assert_i18n(country["name"], f"{prefix}.name")
        assert_i18n(country["description"], f"{prefix}.description")
        assert_best_travel_season(
            country["best_travel_season"], f"{prefix}.best_travel_season"
        )
        if not (1 <= int(country["safety_index"]) <= 5):
            raise ValueError(f"{prefix}.safety_index must be 1–5")
        if float(country["avg_daily_cost_usd"]) <= 0:
            raise ValueError(f"{prefix}.avg_daily_cost_usd must be > 0")

        cities = country.get("cities", [])
        if not isinstance(cities, list) or not cities:
            raise ValueError(f"{prefix}.cities must be a non-empty array")

        for j, city in enumerate(cities):
            cprefix = f"{prefix}.cities[{j}]"
            for field in ("slug", "name", "description", "best_travel_season"):
                if field not in city:
                    raise ValueError(f"{cprefix} missing '{field}'")
            assert_i18n(city["name"], f"{cprefix}.name")
            assert_i18n(city["description"], f"{cprefix}.description")
            assert_best_travel_season(
                city["best_travel_season"], f"{cprefix}.best_travel_season"
            )
            if not (1 <= int(city["safety_index"]) <= 5):
                raise ValueError(f"{cprefix}.safety_index must be 1–5")
            if float(city["avg_daily_cost_usd"]) <= 0:
                raise ValueError(f"{cprefix}.avg_daily_cost_usd must be > 0")
            if "tags" in city and not isinstance(city["tags"], list):
                raise ValueError(f"{cprefix}.tags must be an array")


def pick_fields(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: record[key] for key in allowed if key in record}


def upsert_country(client: Client, country: dict[str, Any]) -> str:
    payload = pick_fields(country, COUNTRY_COLUMNS)
    response = (
        client.table("countries")
        .upsert(payload, on_conflict="iso_code")
        .execute()
    )
    rows = response.data or []
    if not rows:
        lookup = (
            client.table("countries")
            .select("id")
            .eq("iso_code", payload["iso_code"])
            .single()
            .execute()
        )
        if not lookup.data:
            raise RuntimeError(
                f"Country upsert returned no row for iso_code={payload['iso_code']}"
            )
        rows = [lookup.data]

    return rows[0]["id"]


def upsert_city(client: Client, city: dict[str, Any], country_id: str) -> None:
    payload = pick_fields(city, CITY_COLUMNS)
    payload["country_id"] = country_id
    payload.setdefault("tags", [])

    client.table("cities").upsert(
        payload,
        on_conflict="country_id,slug",
    ).execute()


def seed(client: Client, data: dict[str, Any]) -> tuple[int, int]:
    countries = data.get("countries", [])
    country_count = 0
    city_count = 0

    for country in countries:
        country_id = upsert_country(client, country)
        country_count += 1
        iso_code = country["iso_code"]
        print(f"  country upserted: {iso_code} ({country_id})")

        for city in country.get("cities", []):
            upsert_city(client, city, country_id)
            city_count += 1
            tags = city.get("tags", [])
            tag_hint = f" [{', '.join(tags)}]" if tags else ""
            print(f"    city upserted: {city['slug']}{tag_hint}")

    return country_count, city_count


def main() -> None:
    print("GenAI Travel Compass — database seeder")
    print(f"Seed file: {SEED_FILE.relative_to(ROOT_DIR)}")

    url, key = load_config()
    client = create_client(url, key)
    data = load_seed_data()

    try:
        validate_seed(data)
    except ValueError as exc:
        print(f"Invalid seed data: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\nSeeding...")
    country_count, city_count = seed(client, data)

    print(
        f"\nDone. Upserted {country_count} countries and {city_count} cities."
    )


if __name__ == "__main__":
    main()
