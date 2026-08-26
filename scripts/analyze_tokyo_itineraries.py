"""Analyze generated Tokyo itineraries after Approach A reseed."""

from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".scratch" / "tokyo_itineraries"


def hav(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    return 2 * 6371 * asin(
        sqrt(sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
    )


def analyze(path: Path, prefs: list[str]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    sigs = json.loads((ROOT / "data" / "city_signature_pois.json").read_text(encoding="utf-8"))[
        "tokyo"
    ]["pois"]
    sig_names = {p["name"] for p in sigs}

    templeish = night = artfam = nature = 0
    sig_hits: list[str] = []
    day_rows: list[dict] = []

    print("=" * 60)
    print(path.name, "prefs=", prefs)
    print("city=", data.get("city_name"), "total_cost=", data.get("total_cost_usd"))
    print("summary:", (data.get("user_summary") or "")[:240].replace("\n", " "))

    for d in data.get("daily_plans") or []:
        print(
            f"\n  Day {d.get('day_number')} cost={d.get('estimated_daily_cost')} "
            f"theme={d.get('theme')}"
        )
        coords: list[tuple[float, float]] = []
        acts_out = []
        for a in d.get("activities") or []:
            name = str(a.get("poi_name") or "")
            meal = a.get("meal_role")
            cat = a.get("category")
            tags = " ".join(str(t) for t in (a.get("tags") or [])).lower()
            blob = f"{name} {a.get('description')} {tags}".lower()
            mark = ""
            if name in sig_names:
                mark = " [SIGNATURE]"
                sig_hits.append(name)
            if any(t in blob for t in ("temple", "shrine", "jingu", "jinja")):
                templeish += 1
            if any(t in blob for t in ("nightlife", "bar", "club", "golden gai", "yokocho")):
                night += 1
            if any(
                t in blob
                for t in ("art", "family", "museum", "teamlab", "ghibli", "disney")
            ):
                artfam += 1
            if any(t in blob for t in ("park", "garden", "nature")):
                nature += 1
            lat, lon = a.get("lat"), a.get("lon")
            if lat is not None and lon is not None and not meal:
                coords.append((float(lat), float(lon)))
            cost = a.get("cost_usd")
            print(
                f"    {a.get('time_slot')} | {cat}/{meal or '-'} | {name}{mark} | "
                f"photo={bool(a.get('photo_url'))} | cost={cost}"
            )
            acts_out.append(name)
        spans = []
        for i in range(len(coords) - 1):
            s = hav(coords[i], coords[i + 1])
            if s is not None:
                spans.append(s)
        if spans:
            print(
                f"    geo hop km: {[round(s, 1) for s in spans]} "
                f"max={round(max(spans), 1)} sum={round(sum(spans), 1)}"
            )
        day_rows.append({"day": d.get("day_number"), "stops": acts_out, "geo_hops_km": spans})

    print(f"\n  signature_hits={sorted(set(sig_hits))}")
    print(
        f"  counts templeish={templeish} nightlifeish={night} "
        f"art/familyish={artfam} natureish={nature}"
    )
    return {
        "id": path.stem,
        "prefs": prefs,
        "total_cost": data.get("total_cost_usd"),
        "signature_hits": sorted(set(sig_hits)),
        "templeish": templeish,
        "nightlifeish": night,
        "art_familyish": artfam,
        "natureish": nature,
        "days": day_rows,
        "user_summary": data.get("user_summary"),
    }


def main() -> None:
    results = []
    for name, prefs in [
        ("nightlife.json", ["nightlife", "food"]),
        ("culture.json", ["culture", "temple"]),
        ("family_art.json", ["family", "art"]),
    ]:
        results.append(analyze(OUT / name, prefs))
    (OUT / "analysis_deep.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nWrote", OUT / "analysis_deep.json")


if __name__ == "__main__":
    main()
