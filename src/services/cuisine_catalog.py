"""City cuisine catalog — food-type POIs with seeded photos for meal slots."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.schemas.poi import PoiRecord
from src.services.itinerary_i18n import (
    CITY_CUISINE,
    DEFAULT_MEALS,
    cuisine_family,
    meal_description,
)
# from src.services.poi_photos import persistable_photo_url  # meal photo allowlist (disabled)

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = ROOT / "data" / "city_cuisines.json"


@lru_cache
def _photo_map() -> dict[str, str]:
    if not CATALOG_PATH.is_file():
        return {}
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    raw = data.get("photos_by_family") or {}
    return {str(k): str(v) for k, v in raw.items() if v}


def cuisine_photo_url(label: str, meal_role: str = "lunch") -> str:
    """Meal photo lookup (disabled — planner uses lunch/dinner icons).

    Kept for optional manual re-enable: maps dish → Unsplash URL via
    ``data/city_cuisines.json`` ``photos_by_family`` + allowlist.
    """
    _ = (label, meal_role)
    return ""
    # --- meal/food image search (commented out) ---
    # family = cuisine_family(label)
    # photos = _photo_map()
    # # Fail closed: never use a potentially meaningless "other" family photo.
    # url = None if family == "other" else photos.get(family)
    # if not url:
    #     url = photos.get("default_dinner" if meal_role == "dinner" else "default_lunch")
    # return persistable_photo_url(url) or ""


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or "dish"


def cuisine_poi_id(city_id: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cuisine:{city_id}:{_slug(name)}"))


def _city_needle(city_slug: str, city_display: str) -> str | None:
    hay = f"{city_slug} {city_display}".lower()
    for needle, _by_locale in CITY_CUISINE:
        if needle in hay:
            return needle
    return None


def dishes_for_city(
    city_slug: str,
    city_display: str = "",
    *,
    fallback_default: bool = True,
) -> list[dict[str, Any]]:
    """English canonical dishes plus locale names for one city."""
    needle = _city_needle(city_slug, city_display)
    by_locale: dict[str, dict[str, list[str]]] | None = None
    if needle:
        for key, payload in CITY_CUISINE:
            if key == needle:
                by_locale = payload
                break
    dishes: list[dict[str, Any]] = []
    seen: set[str] = set()
    if by_locale:
        en = by_locale.get("en") or {}
        zh = by_locale.get("zh-HK") or en
        ja = by_locale.get("ja") or en
        for role in ("lunch", "dinner"):
            en_list = list(en.get(role) or [])
            zh_list = list(zh.get(role) or [])
            ja_list = list(ja.get(role) or [])
            for i, name in enumerate(en_list):
                if name in seen:
                    continue
                seen.add(name)
                dishes.append(
                    {
                        "name": name,
                        "name_zh": zh_list[i] if i < len(zh_list) else name,
                        "name_ja": ja_list[i] if i < len(ja_list) else name,
                        "role": role,
                        "family": cuisine_family(name),
                    }
                )
        return dishes
    if not fallback_default:
        return []
    lunch, dinner = DEFAULT_MEALS["en"]
    return [
        {
            "name": lunch,
            "name_zh": DEFAULT_MEALS["zh-HK"][0],
            "name_ja": DEFAULT_MEALS["ja"][0],
            "role": "lunch",
            "family": cuisine_family(lunch),
        },
        {
            "name": dinner,
            "name_zh": DEFAULT_MEALS["zh-HK"][1],
            "name_ja": DEFAULT_MEALS["ja"][1],
            "role": "dinner",
            "family": cuisine_family(dinner),
        },
    ]


def cuisine_records(
    *,
    city_slug: str,
    city_id: str,
    city_display: str,
    safety_score: int = 3,
    fallback_default: bool = True,
) -> list[PoiRecord]:
    """PoiRecord rows for ``source=cuisine_catalog`` (meal slots)."""
    records: list[PoiRecord] = []
    for dish in dishes_for_city(
        city_slug, city_display, fallback_default=fallback_default
    ):
        name = str(dish["name"])
        role = str(dish["role"])
        # Meal slots use UI lunch/dinner icons; photo_url left empty for manual fill.
        # Previously: photo = cuisine_photo_url(name, role)
        tags = [
            "food",
            "meal_slot",
            f"cuisine_family:{dish['family']}",
            f"meal_role:{role}",
            f"name_zh-HK:{dish['name_zh']}",
            f"name_ja:{dish['name_ja']}",
        ]
        records.append(
            PoiRecord(
                id=cuisine_poi_id(city_id, name),
                name=name,
                city=city_display,
                category="food",
                description=meal_description(role, city_display, "en", dish=name),
                lat=None,
                lon=None,
                price_level=2,
                rating=None,
                safety_score=safety_score,
                city_id=city_id,
                tags=tags,
                cost_usd=18.0 if role == "lunch" else 28.0,
                duration_minutes=90 if role == "dinner" else 75,
                address=None,
                photo_url=None,
                photo_source="none",
                photo_confidence="low",
                # photo_url=photo or None,
                # photo_source="cuisine_seed" if photo else "none",
                # photo_confidence="high" if photo else "low",
                source="cuisine_catalog",
            )
        )
    return records


def cuisine_tool_dicts(
    *,
    city_slug: str,
    city_id: str,
    city_display: str,
) -> list[dict[str, Any]]:
    """Agent-pool dicts (same contract as search_pois)."""
    out: list[dict[str, Any]] = []
    for rec in cuisine_records(
        city_slug=city_slug,
        city_id=city_id,
        city_display=city_display,
        fallback_default=False,
    ):
        out.append(
            {
                "city_id": city_id,
                "id": rec.id,
                "name": rec.name,
                "category": rec.category,
                "cost_usd": float(rec.cost_usd or 18),
                "duration_minutes": int(rec.duration_minutes or 75),
                "description": rec.description,
                "tags": list(rec.tags),
                "lat": rec.lat,
                "lon": rec.lon,
                "address": rec.address,
                "city": rec.city,
                "photo_url": rec.photo_url,
                "source": rec.source,
            }
        )
    return out


def is_meal_slot_poi(poi: dict[str, Any]) -> bool:
    if str(poi.get("source") or "") == "cuisine_catalog":
        return True
    tags = [str(t).lower() for t in (poi.get("tags") or [])]
    return "meal_slot" in tags or any(t.startswith("cuisine_family:") for t in tags)


def poi_cuisine_family(poi: dict[str, Any]) -> str:
    for tag in poi.get("tags") or []:
        text = str(tag)
        if text.lower().startswith("cuisine_family:"):
            return text.split(":", 1)[1].strip().lower() or cuisine_family(
                str(poi.get("name") or "")
            )
    return cuisine_family(str(poi.get("name") or ""))


def upsert_cuisine_catalog(
    supabase: Any,
    *,
    city_slug: str,
    city_id: str,
    city_display: str,
    safety_score: int = 3,
) -> list[PoiRecord]:
    """Replace cuisine_catalog rows for a city and return the new records."""
    records = cuisine_records(
        city_slug=city_slug,
        city_id=city_id,
        city_display=city_display,
        safety_score=safety_score,
    )
    if not records:
        return []
    now = datetime.now(timezone.utc).isoformat()
    for rec in records:
        rec.photo_checked_at = now
    try:
        supabase.table("pois").delete().eq("city_id", city_id).eq(
            "source", "cuisine_catalog"
        ).execute()
    except Exception:
        pass
    rows = [p.supabase_row() for p in records]
    supabase.table("pois").upsert(rows, on_conflict="id").execute()
    return records

