"""Shared contracts for itinerary quality eval (synthetic names, bad stock photos)."""

from __future__ import annotations

import re
from typing import Any

# Generic seed template suffixes that look fake in the planner UI.
SYNTHETIC_SUFFIXES = (
    "Market Quarter",
    "City Museum",
    "Historic District Walk",
    "Viewpoint Terrace",
    "Architecture Trail",
    "Cultural Landmark",
    "Waterfront Promenade",
    "Neighborhood Discovery",
    "Street Food Lane",
    "Local Bistro District",
    "Cafe Culture Spot",
    "Night Market Bites",
    "Regional Cuisine Hall",
    "Seafood Counter Row",
    "Central Park Pause",
    "Garden Retreat",
    "Wellness Spa Stop",
    "Riverside Rest",
)

_SYNTHETIC_RE = re.compile(
    r"^(?P<city>.+?)\s+(?P<suffix>"
    + "|".join(re.escape(s) for s in SYNTHETIC_SUFFIXES)
    + r")$",
    re.IGNORECASE,
)

# Unsplash photo IDs that were used as mismatched category stock.
BAD_STOCK_PHOTO_IDS = {
    "photo-1469854523086-cc02fe5d8800",  # desert road / van
    "photo-1499856871958-5b9627545d1a",  # Paris Alexandre III bridge
    "photo-1507525428034-b723cf961d3e",  # tropical beach
    "photo-1546069901-ba9599a7e63c",  # salad / poke (old lunch default)
}


def is_synthetic_poi_name(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    return _SYNTHETIC_RE.match(text) is not None


def photo_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"(photo-\d+-[a-f0-9]+)", url, flags=re.IGNORECASE)
    return m.group(1).lower() if m else None


def is_denied_stock_photo(url: str | None) -> bool:
    pid = photo_id_from_url(url)
    if not pid:
        return False
    return pid in {p.lower() for p in BAD_STOCK_PHOTO_IDS}


def contains_cjk(text: str) -> bool:
    return any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in text or "")


def day_meal_roles(activities: list[dict[str, Any]]) -> set[str]:
    roles: set[str] = set()
    for act in activities:
        if act.get("is_food_slot"):
            role = str(act.get("meal_role") or "").lower()
            if role:
                roles.add(role)
    return roles


def attraction_names(activities: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for act in activities:
        if act.get("is_food_slot"):
            continue
        if str(act.get("category") or "") == "attraction":
            out.append(str(act.get("poi_name") or ""))
    return out


def unique_non_meal_photos(plans: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (unique_url_count, total_non_meal_with_photo)."""
    urls: list[str] = []
    for day in plans:
        for act in day.get("activities") or []:
            if act.get("is_food_slot"):
                continue
            url = str(act.get("photo_url") or "").strip()
            if url:
                urls.append(url)
    return len(set(urls)), len(urls)


def unique_lunch_names(plans: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for day in plans:
        for act in day.get("activities") or []:
            if act.get("is_food_slot") and str(act.get("meal_role") or "").lower() == "lunch":
                names.append(str(act.get("poi_name") or ""))
    return names


def parse_slot_minutes(slot: str) -> tuple[int, int] | None:
    text = (slot or "").strip()
    if "-" not in text:
        return None
    start_s, end_s = text.split("-", 1)
    try:
        sh, sm = start_s.strip().split(":", 1)
        eh, em = end_s.strip().split(":", 1)
        return int(sh) * 60 + int(sm), int(eh) * 60 + int(em)
    except ValueError:
        return None


def overlapping_activity_pairs(activities: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return name pairs whose time_slots overlap (adjacent end==start is ok)."""
    ranges: list[tuple[int, int, str]] = []
    for act in activities:
        parsed = parse_slot_minutes(str(act.get("time_slot") or ""))
        if not parsed:
            continue
        start, end = parsed
        ranges.append((start, end, str(act.get("poi_name") or "stop")))
    overlaps: list[tuple[str, str]] = []
    for i, (s1, e1, n1) in enumerate(ranges):
        for s2, e2, n2 in ranges[i + 1 :]:
            if s1 < e2 and s2 < e1:
                overlaps.append((n1, n2))
    return overlaps


def unique_non_meal_poi_names(plans: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (unique_name_count, total_non_meal_named_stops)."""
    names: list[str] = []
    for day in plans:
        for act in day.get("activities") or []:
            if act.get("is_food_slot"):
                continue
            name = str(act.get("poi_name") or "").strip()
            if name:
                names.append(name)
    return len(set(names)), len(names)


def day_meal_families(activities: list[dict[str, Any]]) -> list[str]:
    from src.services.itinerary_i18n import cuisine_family

    families: list[str] = []
    for act in activities:
        if not act.get("is_food_slot"):
            continue
        families.append(cuisine_family(str(act.get("poi_name") or "")))
    return families
