"""Generate + analyze Tokyo itineraries for multiple preference sets."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".scratch" / "tokyo_itineraries_v2"
BASE = "http://127.0.0.1:8000"

CASES = [
    {"id": "nightlife_food", "preferences": ["nightlife", "food"]},
    {"id": "culture", "preferences": ["culture"]},
    {"id": "culture_temple", "preferences": ["culture", "temple"]},
    {"id": "family_art", "preferences": ["family", "art"]},
    {"id": "architecture", "preferences": ["architecture", "history"]},
]


def http_json(method: str, url: str, payload: dict | None = None, timeout: int = 300) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def hav(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    return 2 * 6371 * asin(
        sqrt(sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
    )


def load_sig_names() -> set[str]:
    payload = json.loads((ROOT / "data" / "city_signature_pois.json").read_text(encoding="utf-8"))
    return {p["name"] for p in payload.get("tokyo", {}).get("pois", [])}


def analyze_one(data: dict, prefs: list[str], sig_names: set[str]) -> dict:
    night_tok = ("nightlife", "bar", "pub", "club", "yokocho", "golden gai", "kabukicho")
    temple_tok = ("temple", "shrine", "jingu", "jinja")
    art_tok = ("art", "family", "museum", "teamlab", "ghibli", "disney")
    arch_tok = ("architecture", "heritage", "traditional", "palace", "castle", "monument", "historic")

    days_out = []
    sig_hits: list[str] = []
    night_days = 0
    templeish = artfam = archish = 0

    for d in data.get("daily_plans") or []:
        coords: list[tuple[float, float]] = []
        day_night = 0
        stops = []
        for a in d.get("activities") or []:
            name = str(a.get("poi_name") or "")
            meal = a.get("meal_role")
            blob = f"{name} {a.get('description')} {' '.join(str(t) for t in (a.get('tags') or []))}".lower()
            mark = " [SIG]" if name in sig_names else ""
            if name in sig_names:
                sig_hits.append(name)
            if not meal:
                if any(t in blob for t in night_tok):
                    day_night += 1
                if any(t in blob for t in temple_tok):
                    templeish += 1
                if any(t in blob for t in art_tok):
                    artfam += 1
                if any(t in blob for t in arch_tok):
                    archish += 1
                lat, lon = a.get("lat"), a.get("lon")
                if lat is not None and lon is not None:
                    coords.append((float(lat), float(lon)))
            stops.append(
                {
                    "slot": a.get("time_slot"),
                    "name": name + mark,
                    "cat": a.get("category"),
                    "meal": meal,
                    "photo": bool(a.get("photo_url")),
                    "cost": a.get("cost_usd"),
                }
            )
        hops = []
        for i in range(len(coords) - 1):
            h = hav(coords[i], coords[i + 1])
            if h is not None:
                hops.append(round(h, 1))
        if day_night:
            night_days += 1
        days_out.append(
            {
                "day": d.get("day_number"),
                "cost": d.get("estimated_daily_cost"),
                "theme": d.get("theme"),
                "nightlife_stops": day_night,
                "geo_hops_km": hops,
                "geo_max_km": max(hops) if hops else None,
                "stops": stops,
            }
        )

    return {
        "prefs": prefs,
        "city": data.get("city_name"),
        "total_cost": data.get("total_cost_usd"),
        "user_summary": data.get("user_summary"),
        "signature_hits": sorted(set(sig_hits)),
        "nightlife_days_with_stop": night_days,
        "templeish": templeish,
        "art_familyish": artfam,
        "architectureish": archish,
        "days": days_out,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cities = http_json("GET", f"{BASE}/api/v1/cities?locale=en&limit=200")
    tokyo = next(c for c in cities if str(c.get("slug") or "").lower() == "tokyo")
    city_id = tokyo["id"]
    print("tokyo_id", city_id)
    sig_names = load_sig_names()

    reports = []
    for case in CASES:
        cid = case["id"]
        prefs = case["preferences"]
        print(f"generating {cid} {prefs} ...", flush=True)
        try:
            data = http_json(
                "POST",
                f"{BASE}/api/v1/itineraries/generate",
                {
                    "city_id": city_id,
                    "days": 3,
                    "pace": "moderate",
                    "daily_budget_usd": 130,
                    "preferences": prefs,
                    "locale": "en",
                },
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"  FAIL HTTP {exc.code}: {body[:300]}")
            reports.append({"id": cid, "prefs": prefs, "error": body[:500]})
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {exc}")
            reports.append({"id": cid, "prefs": prefs, "error": str(exc)})
            continue

        (OUT / f"{cid}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = analyze_one(data, prefs, sig_names)
        report["id"] = cid
        reports.append(report)
        print(
            f"  cost={report['total_cost']} sig={len(report['signature_hits'])} "
            f"night_days={report['nightlife_days_with_stop']} "
            f"temple={report['templeish']} art={report['art_familyish']} arch={report['architectureish']}",
            flush=True,
        )

    (OUT / "analysis.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Console summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    for r in reports:
        if r.get("error"):
            print(f"\n[{r['id']}] ERROR: {r['error'][:160]}")
            continue
        print(f"\n[{r['id']}] prefs={r['prefs']} total=${r['total_cost']}")
        print(f"  summary: {(r.get('user_summary') or '')[:180]}")
        print(f"  signatures: {r['signature_hits']}")
        print(
            f"  counts: nightlife_days={r['nightlife_days_with_stop']}/3 "
            f"templeish={r['templeish']} art/family={r['art_familyish']} architecture={r['architectureish']}"
        )
        for d in r["days"]:
            names = [s["name"] for s in d["stops"] if not s.get("meal")]
            print(
                f"  Day {d['day']} (${d['cost']}) night={d['nightlife_stops']} "
                f"hops={d['geo_hops_km']}: {names}"
            )
    print(f"\nWrote {OUT / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
