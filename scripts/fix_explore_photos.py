#!/usr/bin/env python3
"""
Fix Explore photo quality in data/countries_phase6.json.

- Assign a unique working Unsplash URL to every top_city (never reuse country hero).
- Append GE / MA / MX with photo_url + top_cities + cities.
- HEAD-check every URL before writing.

Usage (repo root)::

    python scripts/fix_explore_photos.py
    python scripts/seed_countries.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "countries_phase6.json"


def u(photo_id: str) -> str:
    return (
        f"https://images.unsplash.com/{photo_id}"
        "?auto=format&fit=crop&w=1600&q=80"
    )


# Previously verified working assets (plus extras checked by this script).
POOL: list[str] = [
    u("photo-1502602898657-3e91760cbb34"),
    u("photo-1493976040374-85c8e12f0c0e"),
    u("photo-1516483638261-f4dbaf036963"),
    u("photo-1533105079780-92b9be482077"),
    u("photo-1528127269322-539801943592"),
    u("photo-1469474968028-56623f02e42e"),
    u("photo-1503614472-8c93d56e92ce"),
    u("photo-1507272931001-fc06c17e4f43"),
    u("photo-1530122037265-a5f1f91d3b99"),
    u("photo-1516550893923-42d28e5677af"),
    u("photo-1467269204594-9661b134dd2b"),
    u("photo-1513622470522-26c3c8a854bc"),
    u("photo-1539037116277-4db20889f2d4"),
    u("photo-1534351590666-13e3e96b5017"),
    u("photo-1525625293386-3f8f99389edd"),
    u("photo-1470004914212-05527e49370b"),
    u("photo-1540959733332-eab4deabeeaf"),
    u("photo-1552465011-b4e21bf6e79a"),
    u("photo-1624138784614-87fd1b6528f8"),
    u("photo-1504893524553-b855bce32c67"),
    u("photo-1585208798174-6cedd86e019a"),
    u("photo-1464822759023-fed622ff2c3b"),
    u("photo-1531366936337-7c912a4589a7"),
    u("photo-1583417319070-4a69db38a482"),
    u("photo-1605649487212-47bdab064df7"),
    u("photo-1555990793-da11153b2473"),
    u("photo-1590089415225-401ed6f9db8e"),
    u("photo-1513635269975-59663e0ac1ad"),
    u("photo-1483347756197-71ef80e95f73"),
    u("photo-1570077186671-e9e890419294"),
    u("photo-1552832230-c0197dd311b5"),
    u("photo-1523906834658-6e24ef647b37"),
    u("photo-1583422409516-2895a77efded"),
    u("photo-1558642084-fd07fae5282e"),
    u("photo-1508009603885-50cf7c579365"),
    u("photo-1514395462725-fb4566210144"),
    u("photo-1544551763-46a013bb70d5"),
    u("photo-1476610182048-b716b8518aae"),
    u("photo-1559511260-66a654ae982a"),
    u("photo-1517935706615-2717063c2225"),
    u("photo-1507699622108-4be3abd695ad"),
    u("photo-1560969184-10fe8719e047"),
    u("photo-1549918864-48ac7e0701ed"),
    u("photo-1531360406323-b783504140c4"),
    u("photo-1538332576228-eb5bdf735047"),
    u("photo-1565967511849-76a60a69eac5"),
    u("photo-1555990538-17392d5e18f0"),
    u("photo-1509030450996-ea4694f0cbe0"),
    u("photo-1489749798305-2ed9011178aa"),
    u("photo-1518105779142-d975f22deb17"),
    u("photo-1539020140153-e479b8c22e70"),
    u("photo-1431274172761-fca41d930114"),
    u("photo-1486299267070-83823f5448dd"),
    u("photo-1576924546985-6c3ac4c0b100"),
    u("photo-1441974231531-c6227db76b6e"),
    u("photo-1590559899731-a382839e5549"),
    u("photo-1559592413-7cec4d0cae2b"),
    u("photo-1506973035872-a4ec16b8e8d9"),
    u("photo-1515488764276-beab7607c1e6"),
    u("photo-1578662996442-48f60103fc96"),
    u("photo-1499856871958-5b9627545d1a"),
    u("photo-1565008576549-57569a493712"),
    u("photo-1518638150340-37db5bb3c0c0"),
    u("photo-1558618666-fcd25c85f82e"),
    u("photo-1589394815804-964ed0be2eb5"),
    u("photo-1510092123388-a8d434e6f3c0"),
    u("photo-1524396309943-e03f5249f002"),
    u("photo-1506905925346-21bda4d32df4"),
    u("photo-1589802823080-6ec0fd341655"),
    u("photo-1517154421773-0529f29ea451"),
    u("photo-1538484555286-aeacebabd5b7"),
    u("photo-1569950065884-c8c04f8a3e3e"),
    u("photo-1515658320-7aafae8efad8"),
]

# Prefer thematic matches when the candidate still passes HEAD.
PREFERRED: dict[str, str] = {
    "sydney": u("photo-1624138784614-87fd1b6528f8"),
    "melbourne": u("photo-1514395462725-fb4566210144"),
    "cairns": u("photo-1544551763-46a013bb70d5"),
    "barcelona": u("photo-1583422409516-2895a77efded"),
    "madrid": u("photo-1539037116277-4db20889f2d4"),
    "seville": u("photo-1558642084-fd07fae5282e"),
    "tokyo": u("photo-1540959733332-eab4deabeeaf"),
    "kyoto": u("photo-1493976040374-85c8e12f0c0e"),
    "osaka": u("photo-1590559899731-a382839e5549"),
    "paris": u("photo-1431274172761-fca41d930114"),
    "rome": u("photo-1552832230-c0197dd311b5"),
    "venice": u("photo-1523906834658-6e24ef647b37"),
    "london": u("photo-1486299267070-83823f5448dd"),
    "amsterdam": u("photo-1576924546985-6c3ac4c0b100"),
    "santorini": u("photo-1570077186671-e9e890419294"),
    "reykjavik": u("photo-1476610182048-b716b8518aae"),
    "bangkok": u("photo-1508009603885-50cf7c579365"),
    "marrakech": u("photo-1489749798305-2ed9011178aa"),
    "tbilisi": u("photo-1565008576549-57569a493712"),
    "mexico-city": u("photo-1518105779142-d975f22deb17"),
    "oaxaca": u("photo-1518638150340-37db5bb3c0c0"),
    "lisbon": u("photo-1585208798174-6cedd86e019a"),
    "porto": u("photo-1555881403-64992de360f0"),
    "phuket": u("photo-1552465011-b4e21bf6e79a"),
}


def head_ok(url: str, cache: dict[str, bool]) -> bool:
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "TravelCompassPhotoCheck/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
    except Exception:
        ok = False
    cache[url] = ok
    return ok


def i18n(en: str, zh: str, ja: str) -> dict[str, str]:
    return {"en": en, "zh-HK": zh, "ja": ja}


def season(seasons: list[str], months: list[int], en: str, zh: str, ja: str) -> dict:
    return {
        "seasons": seasons,
        "months": months,
        "label": i18n(en, zh, ja),
    }


def legacy_countries() -> list[dict]:
    spring_autumn = season(
        ["spring", "autumn"], [3, 4, 5, 9, 10, 11], "Spring & Autumn", "春秋", "春と秋"
    )
    winter_spring = season(
        ["winter", "spring"], [11, 12, 1, 2, 3, 4], "Winter & Spring", "冬春", "冬と春"
    )
    summer = season(["summer"], [6, 7, 8, 9], "Summer", "夏季", "夏")

    return [
        {
            "iso_code": "GE",
            "slug": "georgia",
            "name": i18n("Georgia", "格魯吉亞", "ジョージア"),
            "description": i18n(
                "Georgia blends Caucasus mountains, ancient churches, and a generous wine culture. Tbilisi mixes hillside old towns with sulfur baths and inventive cuisine, while wine regions and ski valleys sit within easy reach. Daily costs stay low for Europe-adjacent travel, and hospitality is a point of pride.",
                "格魯吉亞結合高加索山脈、古老教堂與酒文化。第比利斯有山城老區、硫磺浴與創意美食，酒鄉與滑雪區也不遠。相對歐洲成本較低，待客熱情。",
                "ジョージアはコーカサスの山並み、古い教会、ワイン文化が魅力。トビリシは旧市街と温泉、創造的な食が混ざる。欧州近隣としては費用を抑えやすい。",
            ),
            "safety_index": 3,
            "avg_daily_cost_usd": 45,
            "best_travel_season": spring_autumn,
            "region_tags": ["Caucasus"],
            "tags": ["culture", "food", "nature", "budget-friendly", "wine"],
            "photo_url": u("photo-1565008576549-57569a493712"),
            "top_cities": [
                {
                    "slug": "tbilisi",
                    "name": i18n("Tbilisi", "第比利斯", "トビリシ"),
                    "photo_url": "",
                    "description": i18n(
                        "Hillside old town, baths, and modern food scene.",
                        "山城老區、浴場與現代美食。",
                        "斜面の旧市街、温泉、現代的な食。",
                    ),
                    "tags": ["culture", "food", "urban"],
                },
                {
                    "slug": "batumi",
                    "name": i18n("Batumi", "巴統", "バトゥミ"),
                    "photo_url": "",
                    "description": i18n(
                        "Black Sea boulevard and subtropical parks.",
                        "黑海長廊與亞熱帶公園。",
                        "黒海沿いの遊歩道と亜熱帯公園。",
                    ),
                    "tags": ["beach", "urban", "nature"],
                },
            ],
            "cities": [
                {
                    "slug": "tbilisi",
                    "name": i18n("Tbilisi", "第比利斯", "トビリシ"),
                    "description": i18n(
                        "Capital of Georgia with sulfur baths and wine bars.",
                        "格魯吉亞首都，硫磺浴與酒吧。",
                        "ジョージアの首都。温泉とワインバー。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 40,
                    "best_travel_season": spring_autumn,
                    "latitude": 41.7151,
                    "longitude": 44.8271,
                    "tags": [
                        "culture",
                        "food",
                        "nature",
                        "budget-friendly",
                        "off-the-beaten-path",
                    ],
                },
                {
                    "slug": "batumi",
                    "name": i18n("Batumi", "巴統", "バトゥミ"),
                    "description": i18n(
                        "Black Sea resort city with a lively promenade.",
                        "黑海度假城，長廊熱鬧。",
                        "黒海リゾート。遊歩道がにぎやか。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 45,
                    "best_travel_season": summer,
                    "latitude": 41.6168,
                    "longitude": 41.6367,
                    "tags": ["beach", "urban", "budget-friendly"],
                },
            ],
        },
        {
            "iso_code": "MA",
            "slug": "morocco",
            "name": i18n("Morocco", "摩洛哥", "モロッコ"),
            "description": i18n(
                "Morocco offers medina labyrinths, desert edges, and Atlantic light within a compact itinerary. Marrakech pulses with souks and riads, while coastal and imperial cities add quieter rhythms. Spices, tagines, and mint tea frame every day.",
                "摩洛哥有迷宮式舊城、沙漠邊緣與大西洋光線。馬拉喀什市集與庭院旅館熱鬧，海岸與皇城節奏較慢。香料、塔吉鍋與薄荷茶貫穿日常。",
                "モロッコは迷路のようなメディナ、砂漠の端、大西洋の光が魅力。マラケシュはスークとリヤードが活気的で、海岸や古都は穏やか。",
            ),
            "safety_index": 3,
            "avg_daily_cost_usd": 50,
            "best_travel_season": spring_autumn,
            "region_tags": ["North Africa"],
            "tags": ["culture", "adventure", "food", "desert"],
            "photo_url": u("photo-1489749798305-2ed9011178aa"),
            "top_cities": [
                {
                    "slug": "marrakech",
                    "name": i18n("Marrakech", "馬拉喀什", "マラケシュ"),
                    "photo_url": "",
                    "description": i18n(
                        "Souks, riads, and Atlas day trips.",
                        "市集、庭院旅館與阿特拉斯一日遊。",
                        "スーク、リヤード、アトラス日帰り。",
                    ),
                    "tags": ["culture", "food", "adventure"],
                },
                {
                    "slug": "fez",
                    "name": i18n("Fez", "非斯", "フェズ"),
                    "photo_url": "",
                    "description": i18n(
                        "Medieval medina and artisan workshops.",
                        "中世紀舊城與工匠作坊。",
                        "中世メディナと工芸の街。",
                    ),
                    "tags": ["culture", "history"],
                },
            ],
            "cities": [
                {
                    "slug": "marrakech",
                    "name": i18n("Marrakech", "馬拉喀什", "マラケシュ"),
                    "description": i18n(
                        "Red-walled city of souks and palm gardens.",
                        "紅牆之城，市集與棕櫚園。",
                        "赤い壁の都市。スークとヤシの庭。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 55,
                    "best_travel_season": spring_autumn,
                    "latitude": 31.6295,
                    "longitude": -7.9811,
                    "tags": ["culture", "adventure", "food"],
                },
                {
                    "slug": "fez",
                    "name": i18n("Fez", "非斯", "フェズ"),
                    "description": i18n(
                        "Imperial city with a vast pedestrian medina.",
                        "皇城，步行舊城廣闊。",
                        "広大な歩行者メディナの古都。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 48,
                    "best_travel_season": spring_autumn,
                    "latitude": 34.0181,
                    "longitude": -5.0078,
                    "tags": ["culture", "history", "food"],
                },
            ],
        },
        {
            "iso_code": "MX",
            "slug": "mexico",
            "name": i18n("Mexico", "墨西哥", "メキシコ"),
            "description": i18n(
                "Mexico rewards curious travelers with regional cuisine, colonial plazas, and Caribbean or Pacific coasts. Cities like Oaxaca spotlight markets and crafts, while beach hubs and archaeological sites fill longer trips.",
                "墨西哥有各地美食、殖民廣場與加勒比／太平洋海岸。瓦哈卡以市集與工藝聞名，海灘與考古遺址適合長途。",
                "メキシコは地方料理、コロニアル広場、カリブ／太平洋岸が魅力。オアハカは市場と工芸、ビーチと遺跡は長期向け。",
            ),
            "safety_index": 3,
            "avg_daily_cost_usd": 55,
            "best_travel_season": winter_spring,
            "region_tags": ["North America", "Latin America"],
            "tags": ["culture", "food", "beach", "budget-friendly"],
            "photo_url": u("photo-1518105779142-d975f22deb17"),
            "top_cities": [
                {
                    "slug": "oaxaca",
                    "name": i18n("Oaxaca", "瓦哈卡", "オアハカ"),
                    "photo_url": "",
                    "description": i18n(
                        "Markets, mole, and artisan workshops.",
                        "市集、莫勒醬與工藝坊。",
                        "市場、モレ、工芸工房。",
                    ),
                    "tags": ["culture", "food"],
                },
                {
                    "slug": "mexico-city",
                    "name": i18n("Mexico City", "墨西哥城", "メキシコシティ"),
                    "photo_url": "",
                    "description": i18n(
                        "Museums, neighborhoods, and world-class food.",
                        "博物館、街區與一流美食。",
                        "博物館、街歩き、一流の食。",
                    ),
                    "tags": ["culture", "food", "urban"],
                },
            ],
            "cities": [
                {
                    "slug": "oaxaca",
                    "name": i18n("Oaxaca", "瓦哈卡", "オアハカ"),
                    "description": i18n(
                        "Colonial city famous for markets and cuisine.",
                        "以市集與美食聞名的殖民城市。",
                        "市場と食で知られるコロニアル都市。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 50,
                    "best_travel_season": winter_spring,
                    "latitude": 17.0732,
                    "longitude": -96.7266,
                    "tags": [
                        "culture",
                        "food",
                        "off-the-beaten-path",
                        "budget-friendly",
                    ],
                },
                {
                    "slug": "mexico-city",
                    "name": i18n("Mexico City", "墨西哥城", "メキシコシティ"),
                    "description": i18n(
                        "Vast capital of museums, parks, and street food.",
                        "博物館、公園與街頭小吃之都。",
                        "博物館・公園・屋台の大首都。",
                    ),
                    "safety_index": 3,
                    "avg_daily_cost_usd": 60,
                    "best_travel_season": winter_spring,
                    "latitude": 19.4326,
                    "longitude": -99.1332,
                    "tags": ["culture", "food", "urban"],
                },
            ],
        },
    ]


def pick_url(
    slug: str,
    used: set[str],
    exclude: set[str],
    cache: dict[str, bool],
    pool: list[str],
) -> str:
    candidates: list[str] = []
    pref = PREFERRED.get(slug)
    if pref:
        candidates.append(pref)
    candidates.extend(pool)
    for url in candidates:
        if url in used or url in exclude:
            continue
        if head_ok(url, cache):
            return url
    raise RuntimeError(f"No unique working photo left for slug={slug}")


def main() -> int:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    countries: list[dict] = data["countries"]
    existing = {c["iso_code"] for c in countries}
    for legacy in legacy_countries():
        if legacy["iso_code"] not in existing:
            countries.append(legacy)
            print(f"+ added {legacy['iso_code']}")
        else:
            # Refresh photo / top_cities / cities on existing seed row
            for i, c in enumerate(countries):
                if c["iso_code"] == legacy["iso_code"]:
                    countries[i] = legacy
                    print(f"* refreshed {legacy['iso_code']}")
                    break

    cache: dict[str, bool] = {}
    print("Checking photo pool…")
    good_pool = [url for url in POOL if head_ok(url, cache)]
    print(f"  pool ok={len(good_pool)}/{len(POOL)}")
    if len(good_pool) < 8:
        print("Not enough working Unsplash URLs in pool", file=sys.stderr)
        return 1

    # Country heroes: keep existing working URL, else pick from pool.
    # City uniqueness is per-country (vs country hero + sibling cities).
    for c in countries:
        country_url = c.get("photo_url") or ""
        if not (country_url and head_ok(country_url, cache)):
            country_url = pick_url(c["slug"], set(), set(), cache, good_pool)
            c["photo_url"] = country_url

    for c in countries:
        country_url = c["photo_url"]
        tops = c.get("top_cities") or []
        if not tops:
            print(f"ERROR: {c['iso_code']} has no top_cities", file=sys.stderr)
            return 1
        used_in_country: set[str] = {country_url}
        for t in tops:
            slug = t["slug"]
            url = pick_url(slug, used_in_country, set(), cache, good_pool)
            t["photo_url"] = url
            used_in_country.add(url)
            print(f"  {c['iso_code']} {slug:20} {url.split('photo-')[-1][:36]}")

    # Final validation
    same = 0
    empty = 0
    missing_cities = 0
    intra_dup = 0
    for c in countries:
        if not c.get("photo_url"):
            empty += 1
        tops = c.get("top_cities") or []
        if not tops:
            missing_cities += 1
        seen: set[str] = set()
        for t in tops:
            p = t.get("photo_url") or ""
            if not p:
                empty += 1
            if p == c.get("photo_url"):
                same += 1
            if p in seen:
                intra_dup += 1
            seen.add(p)

    if empty or missing_cities or same or intra_dup:
        print(
            f"VALIDATION FAIL empty={empty} missing_cities={missing_cities} "
            f"same_as_country={same} intra_dup={intra_dup}",
            file=sys.stderr,
        )
        return 1

    data["countries"] = countries
    SEED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {SEED.relative_to(ROOT)} countries={len(countries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
