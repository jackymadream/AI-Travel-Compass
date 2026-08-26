#!/usr/bin/env python3
"""
End-to-end itinerary flow eval: controls → expected → generate → compare.

Requires a running FastAPI API (default http://127.0.0.1:8000) and seeded POIs.

Usage::

    python scripts/eval_itinerary_flow.py
    python scripts/eval_itinerary_flow.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.itinerary_eval import (  # noqa: E402
    attraction_names,
    contains_cjk,
    day_meal_families,
    day_meal_roles,
    is_denied_stock_photo,
    is_synthetic_poi_name,
    overlapping_activity_pairs,
    unique_lunch_names,
    unique_non_meal_photos,
    unique_non_meal_poi_names,
)
from src.services.agent_tools import PACE_LIMITS, scheduled_total_minutes  # noqa: E402

REPORT_DIR = ROOT / ".scratch" / "eval-itinerary"

# city_slug → expectations
CASES: list[dict[str, Any]] = [
    {
        "id": "osaka_zh_hk_food_anime",
        "slug": "osaka",
        "days": 3,
        "pace": "moderate",
        "daily_budget_usd": 100,
        "preferences": ["food", "nightlife", "street-food", "anime"],
        "locale": "zh-HK",
        "expect_city_substrings": ["大阪", "Osaka"],
        "expect_cjk_narrative": True,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "tokyo_ja",
        "slug": "tokyo",
        "days": 2,
        "pace": "relaxed",
        "daily_budget_usd": 120,
        "preferences": ["culture", "food"],
        "locale": "ja",
        "expect_city_substrings": ["東京", "Tokyo"],
        "expect_cjk_narrative": True,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "paris_en",
        "slug": "paris",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 150,
        "preferences": ["culture", "food", "museums"],
        "locale": "en",
        "expect_city_substrings": ["Paris"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "marrakech_desert",
        "slug": "marrakech",
        "days": 1,
        "pace": "moderate",
        "daily_budget_usd": 90,
        "preferences": ["desert", "culture", "markets"],
        "locale": "en",
        "expect_city_substrings": ["Marrakech", "Marrakesh"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "tokyo_nightlife_only",
        "slug": "tokyo",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 120,
        "preferences": ["nightlife"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": False,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["nightlife"],
    },
    {
        "id": "tokyo_nightlife_food",
        "slug": "tokyo",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 130,
        "preferences": ["nightlife", "food"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["nightlife"],
    },
    {
        "id": "tokyo_family_art",
        "slug": "tokyo",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 140,
        "preferences": ["family", "art"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["family", "art"],
        "forbid_all_temple_attractions": True,
    },
    {
        "id": "tokyo_nature_rest",
        "slug": "tokyo",
        "days": 2,
        "pace": "relaxed",
        "daily_budget_usd": 100,
        "preferences": ["nature", "park"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["nature", "park"],
    },
    {
        "id": "tokyo_culture_temple",
        "slug": "tokyo",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 110,
        "preferences": ["culture", "temple"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["culture", "temple"],
    },
    {
        "id": "kyoto_en_nature_3day",
        "slug": "kyoto",
        "days": 3,
        "pace": "moderate",
        "daily_budget_usd": 100,
        "preferences": ["popular", "nature", "quiet gardens", "kid-friendly"],
        "locale": "en",
        "expect_city_substrings": ["Kyoto", "京都"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_strict_unique_attractions": True,
    },
    {
        "id": "tokyo_moderate_4day",
        "slug": "tokyo",
        "days": 4,
        "pace": "moderate",
        "daily_budget_usd": 120,
        "preferences": ["culture", "food"],
        "locale": "en",
        "expect_city_substrings": ["Tokyo"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "seoul_en_culture_nightlife",
        "slug": "seoul",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 120,
        "preferences": ["culture", "nightlife", "museum"],
        "locale": "en",
        "expect_city_substrings": ["Seoul"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["nightlife"],
    },
    {
        "id": "rome_en_history_art",
        "slug": "rome",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 140,
        "preferences": ["culture", "history", "art", "museum"],
        "locale": "en",
        "expect_city_substrings": ["Rome"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
    {
        "id": "barcelona_en_architecture_family",
        "slug": "barcelona",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 130,
        "preferences": ["architecture", "art", "family"],
        "locale": "en",
        "expect_city_substrings": ["Barcelona"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["family", "art"],
    },
    {
        "id": "bangkok_en_temple_nightlife",
        "slug": "bangkok",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 100,
        "preferences": ["culture", "temple", "nightlife", "street-food"],
        "locale": "en",
        "expect_city_substrings": ["Bangkok"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["nightlife"],
    },
    {
        "id": "london_en_museum_park",
        "slug": "london",
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 150,
        "preferences": ["museum", "culture", "park", "nature"],
        "locale": "en",
        "expect_city_substrings": ["London"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
        "require_preference_coverage": ["museum", "park"],
    },
    {
        "id": "reykjavik_en_nature_viewpoint",
        "slug": "reykjavik",
        "days": 2,
        "pace": "relaxed",
        "daily_budget_usd": 160,
        "preferences": ["nature", "viewpoint", "museum", "family"],
        "locale": "en",
        "expect_city_substrings": ["Reykjavik", "Reykjavík"],
        "expect_cjk_narrative": False,
        "forbid_synthetic_attractions": True,
        "forbid_denied_photos": True,
        "require_meals": True,
    },
]


def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_city_id(base: str, slug: str) -> str | None:
    cities = http_json("GET", f"{base.rstrip('/')}/api/v1/cities?locale=en")
    if not isinstance(cities, list):
        return None
    for row in cities:
        if str(row.get("slug") or "").lower() == slug.lower():
            return str(row["id"])
    return None


def evaluate_case(base: str, case: dict[str, Any]) -> dict[str, Any]:
    city_id = resolve_city_id(base, case["slug"])
    predicted = {
        "city_slug": case["slug"],
        "locale": case["locale"],
        "preferences": case["preferences"],
        "expect_city_substrings": case["expect_city_substrings"],
        "expect_cjk": case["expect_cjk_narrative"],
        "forbid_synthetic": case["forbid_synthetic_attractions"],
    }
    result: dict[str, Any] = {
        "id": case["id"],
        "predicted": predicted,
        "ok": False,
        "checks": [],
        "errors": [],
    }
    if not city_id:
        result["errors"].append(f"city slug {case['slug']!r} not found")
        return result

    try:
        data = http_json(
            "POST",
            f"{base.rstrip('/')}/api/v1/itineraries/generate",
            {
                "city_id": city_id,
                "days": case["days"],
                "pace": case["pace"],
                "daily_budget_usd": case["daily_budget_usd"],
                "preferences": case["preferences"],
                "locale": case["locale"],
            },
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        result["errors"].append(f"HTTP {exc.code}: {body[:400]}")
        return result
    except urllib.error.URLError as exc:
        result["errors"].append(f"API unreachable: {exc}")
        return result

    result["actual_city_name"] = data.get("city_name")
    result["actual_days"] = len(data.get("daily_plans") or [])
    checks: list[dict[str, Any]] = []

    city_name = str(data.get("city_name") or "")
    city_ok = any(s.lower() in city_name.lower() for s in case["expect_city_substrings"])
    checks.append({"name": "city_name", "ok": city_ok, "detail": city_name})

    plans = data.get("daily_plans") or []
    days_ok = len(plans) == case["days"]
    checks.append(
        {
            "name": "all_days_returned",
            "ok": days_ok,
            "detail": f"{len(plans)}/{case['days']}",
        }
    )
    meals_ok = True
    synth_hits: list[str] = []
    denied_photos: list[str] = []
    meals_missing_id: list[str] = []
    meals_missing_photo: list[str] = []
    narrative_bits = [
        city_name,
        str(data.get("agent_reasoning") or ""),
        *[str(d.get("theme") or "") for d in plans],
    ]

    for day in plans:
        acts = day.get("activities") or []
        roles = day_meal_roles(acts)
        if case.get("require_meals") and not ({"lunch", "dinner"} <= roles):
            meals_ok = False
        for name in attraction_names(acts):
            if case.get("forbid_synthetic_attractions") and is_synthetic_poi_name(name):
                synth_hits.append(name)
        for act in acts:
            url = act.get("photo_url")
            if case.get("forbid_denied_photos") and is_denied_stock_photo(url):
                denied_photos.append(f"{act.get('poi_name')}: {url}")
            if act.get("is_food_slot"):
                narrative_bits.append(str(act.get("poi_name") or ""))
                narrative_bits.append(str(act.get("description") or ""))
                if case.get("require_meals"):
                    if not act.get("poi_id"):
                        meals_missing_id.append(str(act.get("poi_name") or ""))
                    # Meal stock photos disabled — UI uses lunch/dinner icons.
                    if case.get("require_meal_photos") and not str(url or "").strip():
                        meals_missing_photo.append(str(act.get("poi_name") or ""))

    checks.append({"name": "meals_lunch_dinner", "ok": meals_ok, "detail": meals_ok})
    checks.append(
        {
            "name": "meals_from_food_pool",
            "ok": len(meals_missing_id) == 0,
            "detail": meals_missing_id[:5],
        }
    )
    checks.append(
        {
            "name": "meals_have_photo",
            "ok": len(meals_missing_photo) == 0,
            "detail": meals_missing_photo[:5],
        }
    )
    synth_ok = len(synth_hits) == 0
    checks.append(
        {
            "name": "no_synthetic_attractions",
            "ok": synth_ok,
            "detail": synth_hits[:5],
        }
    )
    photos_ok = len(denied_photos) == 0
    checks.append(
        {
            "name": "no_denied_stock_photos",
            "ok": photos_ok,
            "detail": denied_photos[:5],
        }
    )

    if case.get("expect_cjk_narrative"):
        joined = " ".join(narrative_bits)
        cjk_ok = contains_cjk(joined)
        checks.append({"name": "cjk_narrative", "ok": cjk_ok, "detail": joined[:120]})
    else:
        checks.append({"name": "cjk_narrative", "ok": True, "detail": "skipped"})

    unique_photos, photo_total = unique_non_meal_photos(plans)
    photo_threshold = min(photo_total, max(1, int(0.8 * photo_total))) if photo_total else 0
    photos_unique_ok = photo_total == 0 or unique_photos >= photo_threshold
    checks.append(
        {
            "name": "unique_non_meal_photos",
            "ok": photos_unique_ok,
            "detail": f"{unique_photos}/{photo_total} (need >= {photo_threshold})",
        }
    )

    lunches = unique_lunch_names(plans)
    days_n = len(plans)
    lunch_ok = days_n <= 1 or len(set(lunches)) >= max(1, days_n - 1)
    checks.append(
        {
            "name": "varied_lunch_labels",
            "ok": lunch_ok,
            "detail": lunches,
        }
    )

    unique_names, name_total = unique_non_meal_poi_names(plans)
    rest_days = sum(
        1
        for d in plans
        for a in (d.get("activities") or [])
        if not a.get("is_food_slot") and str(a.get("category") or "") == "rest"
    )
    # Allow one rest recycle only when rest stops outnumber a tiny leftover pool.
    names_ok = unique_names == name_total or (
        rest_days > 0 and unique_names >= max(1, name_total - 1)
    )
    if case.get("require_strict_unique_attractions"):
        attraction_labels = [
            str(a.get("poi_name") or "")
            for d in plans
            for a in (d.get("activities") or [])
            if not a.get("is_food_slot")
            and str(a.get("category") or "") == "attraction"
        ]
        names_ok = len(attraction_labels) == len({n for n in attraction_labels if n})
    checks.append(
        {
            "name": "unique_non_meal_poi_names",
            "ok": names_ok,
            "detail": f"{unique_names}/{name_total}",
        }
    )

    overlap_hits: list[str] = []
    family_clash: list[str] = []
    for day in plans:
        acts = day.get("activities") or []
        for a, b in overlapping_activity_pairs(acts):
            overlap_hits.append(f"day {day.get('day_number')}: {a} / {b}")
        families = day_meal_families(acts)
        if families and len(families) != len(set(families)):
            family_clash.append(
                f"day {day.get('day_number')}: {families}"
            )
    checks.append(
        {
            "name": "no_overlapping_slots",
            "ok": len(overlap_hits) == 0,
            "detail": overlap_hits[:5],
        }
    )

    limits = PACE_LIMITS.get(str(case.get("pace") or "moderate").lower())
    pace_issues: list[str] = []
    if limits:
        for day in plans:
            acts = day.get("activities") or []
            total = scheduled_total_minutes(acts)
            over = (
                len(acts) > limits["max_activities"]
                or total > limits["max_duration_minutes"]
            )
            day_warnings = day.get("warnings") or []
            if over and not day_warnings:
                pace_issues.append(
                    f"day {day.get('day_number')}: {len(acts)} stops / "
                    f"{total} min (max {limits['max_activities']} / "
                    f"{limits['max_duration_minutes']}) without warnings"
                )
    checks.append(
        {
            "name": "pace_caps_or_day_warnings",
            "ok": len(pace_issues) == 0,
            "detail": pace_issues[:5] or "within caps or warned",
        }
    )
    checks.append(
        {
            "name": "unique_meal_families_per_day",
            "ok": len(family_clash) == 0,
            "detail": family_clash[:5],
        }
    )

    required_tags = [str(t).lower() for t in case.get("require_preference_coverage") or []]
    if required_tags:
        hay = " ".join(
            [
                str(data.get("user_summary") or ""),
                str(data.get("agent_reasoning") or ""),
                *[
                    f"{a.get('poi_name')} {a.get('description')} {a.get('category')}"
                    for d in plans
                    for a in (d.get("activities") or [])
                ],
            ]
        ).lower()
        missing = [tag for tag in required_tags if tag not in hay and tag.replace("-", " ") not in hay]
        checks.append(
            {
                "name": "preference_coverage",
                "ok": len(missing) == 0,
                "detail": missing or required_tags,
            }
        )

    if case.get("forbid_all_temple_attractions"):
        temple_hits = [
            str(a.get("poi_name") or "")
            for d in plans
            for a in (d.get("activities") or [])
            if not a.get("is_food_slot")
            and any(
                tok in f"{a.get('poi_name')} {a.get('description')}".lower()
                for tok in ("temple", "shrine", "jingu", "jinja")
            )
        ]
        non_temple = [
            str(a.get("poi_name") or "")
            for d in plans
            for a in (d.get("activities") or [])
            if not a.get("is_food_slot")
            and str(a.get("category") or "") == "attraction"
            and str(a.get("poi_name") or "") not in temple_hits
        ]
        # Soft: not every attraction may be a temple when family/art prefs are set.
        temple_ok = len(non_temple) > 0 or len(temple_hits) == 0
        checks.append(
            {
                "name": "not_all_temple_attractions",
                "ok": temple_ok,
                "detail": {"temple_hits": temple_hits[:5], "other": non_temple[:5]},
            }
        )

    result["checks"] = checks
    result["ok"] = all(c["ok"] for c in checks)
    result["sample_attractions"] = [
        a.get("poi_name")
        for d in plans[:1]
        for a in (d.get("activities") or [])
        if a.get("category") == "attraction"
    ][:5]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--slug",
        action="append",
        default=[],
        help="Only run cases for these city slugs (repeatable).",
    )
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failures = 0
    selected = CASES
    if args.slug:
        want = {s.lower() for s in args.slug}
        selected = [c for c in CASES if str(c["slug"]).lower() in want]

    print("Itinerary flow eval (controls → generate → compare)")
    print(f"API: {args.base_url}")
    for case in selected:
        print(f"\nCASE {case['id']}")
        print(
            f"  predict: slug={case['slug']} locale={case['locale']} "
            f"prefs={case['preferences']}"
        )
        row = evaluate_case(args.base_url, case)
        results.append(row)
        status = "PASS" if row["ok"] else "FAIL"
        if not row["ok"]:
            failures += 1
        print(f"  {status} city={row.get('actual_city_name')!r}")
        for err in row.get("errors") or []:
            print(f"    error: {err}")
        for check in row.get("checks") or []:
            mark = "ok" if check["ok"] else "X "
            print(f"    [{mark}] {check['name']}: {check.get('detail')!r}")
        if row.get("sample_attractions"):
            print(f"    sample attractions: {row['sample_attractions']}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPORT_DIR / f"report_{stamp}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"{'All passed' if failures == 0 else f'{failures} case(s) failed'}.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
