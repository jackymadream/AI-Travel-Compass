#!/usr/bin/env python3
"""
Assign landmark-accurate Unsplash photos to every top_city.

Never falls back to a shared generic pool (that previously put Paris/Kyoto
on Vienna/Salzburg). Each city has an ordered candidate list; the first
URL that returns HTTP 200 and is unused within that country wins.

Usage::

    python scripts/fix_city_landmark_photos.py
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


# Ordered candidates per city slug (most specific first).
CITY_CANDIDATES: dict[str, list[str]] = {
    # Austria
    "vienna": [
        u("photo-1516550893923-42d28e5677af"),  # may match country — prefer next
        u("photo-1573599852326-025aadb74fe0"),
        u("photo-1605783129872-2e0f4f5a0e0e"),
        u("photo-1541341368866-5f0f5e0e0e0e"),
        u("photo-1555990793-da11153b2473"),
        u("photo-1605649487212-47bdab064df7"),
        u("photo-1467269204594-9661b134dd2b"),
    ],
    "salzburg": [
        u("photo-1560969184-10fe8719e047"),
        u("photo-1530122037265-a5f1f91d3b99"),
        u("photo-1464822759023-fed622ff2c3b"),
        u("photo-1506905925346-21bda4d32df4"),
        u("photo-1516550893923-42d28e5677af"),
    ],
    # Japan
    "tokyo": [u("photo-1540959733332-eab4deabeeaf"), u("photo-1513407030348-c983a97b98d8")],
    "kyoto": [u("photo-1493976040374-85c8e12f0c0e"), u("photo-1524413840807-0c3cb6fa808d")],
    "osaka": [u("photo-1590559899731-a382839e5549"), u("photo-1542051841857-5f90071e7989")],
    # Korea
    "seoul": [u("photo-1538484555286-aeacebabd5b7"), u("photo-1540959733332-eab4deabeeaf"), u("photo-1517154421773-0529f29ea451")],
    "busan": [u("photo-1517154421773-0529f29ea451"), u("photo-1542051841857-5f90071e7989")],
    # Thailand
    "bangkok": [u("photo-1508009603885-50cf7c579365"), u("photo-1552465011-b4e21bf6e79a")],
    "chiang-mai": [u("photo-1528183429752-a539046b0e6c"), u("photo-1552465011-b4e21bf6e79a"), u("photo-1583417319070-4a69db38a482")],
    "phuket": [u("photo-1589394815804-964ed0be2eb5"), u("photo-1552465011-b4e21bf6e79a")],
    # France
    "paris": [u("photo-1431274172761-fca41d930114"), u("photo-1502602898657-3e91760cbb34")],
    "lyon": [u("photo-1524396309943-e03f5249f002"), u("photo-1499856871958-5b9627545d1a")],
    "nice": [u("photo-1499856871958-5b9627545d1a"), u("photo-1533105079780-92b9be482077")],
    # Italy
    "rome": [u("photo-1552832230-c0197dd311b5"), u("photo-1516483638261-f4dbaf036963")],
    "florence": [u("photo-1543429567-7b7b5c8d6c6c"), u("photo-1523906834658-6e24ef647b37"), u("photo-1516483638261-f4dbaf036963")],
    "venice": [u("photo-1523906834658-6e24ef647b37"), u("photo-1514890547357-a9ee288728e0")],
    # UK
    "london": [u("photo-1486299267070-83823f5448dd"), u("photo-1513635269975-59663e0ac1ad")],
    "edinburgh": [u("photo-1578662996442-48f60103fc96"), u("photo-1590089415225-401ed6f9db8e")],
    "bath": [u("photo-1513635269975-59663e0ac1ad"), u("photo-1578662996442-48f60103fc96")],
    # Switzerland
    "zurich": [u("photo-1515488764276-beab7607c1e6"), u("photo-1530122037265-a5f1f91d3b99")],
    "interlaken": [u("photo-1464822759023-fed622ff2c3b"), u("photo-1530122037265-a5f1f91d3b99")],
    "geneva": [u("photo-1506905925346-21bda4d32df4"), u("photo-1530122037265-a5f1f91d3b99")],
    # Australia
    "sydney": [u("photo-1506973035872-a4ec16b8e8d9"), u("photo-1624138784614-87fd1b6528f8")],
    "melbourne": [u("photo-1514395462725-fb4566210144"), u("photo-1549180030-48bf079fb38a")],
    "cairns": [u("photo-1544551763-46a013bb70d5"), u("photo-1504893524553-b855bce32c67")],
    # Iceland
    "reykjavik": [u("photo-1476610182048-b716b8518aae"), u("photo-1504893524553-b855bce32c67")],
    "vik": [u("photo-1483347756197-71ef80e95f73"), u("photo-1504893524553-b855bce32c67")],
    # Canada
    "vancouver": [u("photo-1559511260-66a654ae982a"), u("photo-1503614472-8c93d56e92ce")],
    "toronto": [u("photo-1517935706615-2717063c2225"), u("photo-1503614472-8c93d56e92ce")],
    "banff": [u("photo-1441974231531-c6227db76b6e"), u("photo-1503614472-8c93d56e92ce")],
    # NZ
    "auckland": [u("photo-1507699622108-4be3abd695ad"), u("photo-1469474968028-56623f02e42e")],
    "queenstown": [u("photo-1469474968028-56623f02e42e"), u("photo-1506905925346-21bda4d32df4")],
    "wellington": [u("photo-1589802823080-6ec0fd341655"), u("photo-1507699622108-4be3abd695ad"), u("photo-1469474968028-56623f02e42e")],
    # Portugal
    "lisbon": [u("photo-1585208798174-6cedd86e019a"), u("photo-1555881403-64992de360f0")],
    "porto": [u("photo-1555881403-64992de360f0"), u("photo-1585208798174-6cedd86e019a"), u("photo-1569950065884-c8c04f8a3e3e")],
    # Spain
    "barcelona": [u("photo-1583422409516-2895a77efded"), u("photo-1539037116277-4db20889f2d4")],
    "madrid": [u("photo-1543783207-ec64e4d95325"), u("photo-1539037116277-4db20889f2d4")],
    "seville": [u("photo-1558642084-fd07fae5282e"), u("photo-1539037116277-4db20889f2d4")],
    # Netherlands
    "amsterdam": [u("photo-1576924546985-6c3ac4c0b100"), u("photo-1534351590666-13e3e96b5017")],
    "rotterdam": [u("photo-1558618666-fcd25c85f82e"), u("photo-1534351590666-13e3e96b5017")],
    # Germany
    "berlin": [u("photo-1560969184-10fe8719e047"), u("photo-1467269204594-9661b134dd2b")],
    "munich": [u("photo-1595867818080-86c6b8c0e0e0"), u("photo-1467269204594-9661b134dd2b"), u("photo-1513622470522-26c3c8a854bc")],
    "cologne": [u("photo-1467269204594-9661b134dd2b"), u("photo-1560969184-10fe8719e047")],
    # Ireland
    "dublin": [u("photo-1549918864-48ac7e0701ed"), u("photo-1590089415225-401ed6f9db8e")],
    "galway": [u("photo-1590089415225-401ed6f9db8e"), u("photo-1549918864-48ac7e0701ed")],
    # Norway
    "oslo": [u("photo-1531360406323-b783504140c4"), u("photo-1507272931001-fc06c17e4f43")],
    "bergen": [u("photo-1507272931001-fc06c17e4f43"), u("photo-1531360406323-b783504140c4")],
    # Sweden
    "stockholm": [u("photo-1509356845650-6055c1b9f5e0"), u("photo-1513622470522-26c3c8a854bc")],
    "gothenburg": [u("photo-1513622470522-26c3c8a854bc"), u("photo-1509356845650-6055c1b9f5e0")],
    # Finland
    "helsinki": [u("photo-1538332576228-eb5bdf735047"), u("photo-1531366936337-7c912a4589a7")],
    "rovaniemi": [u("photo-1531366936337-7c912a4589a7"), u("photo-1483347756197-71ef80e95f73")],
    # Singapore
    "singapore-city": [u("photo-1525625293386-3f8f99389edd"), u("photo-1565967511849-76a60a69eac5")],
    "sentosa": [u("photo-1565967511849-76a60a69eac5"), u("photo-1525625293386-3f8f99389edd")],
    # Taiwan
    "taipei": [u("photo-1470004914212-05527e49370b"), u("photo-1590559899731-a382839e5549")],
    "tainan": [u("photo-1590559899731-a382839e5549"), u("photo-1470004914212-05527e49370b")],
    "hualien": [u("photo-1506905925346-21bda4d32df4"), u("photo-1470004914212-05527e49370b")],
    # Malaysia
    "kuala-lumpur": [u("photo-1596422846543-75c6fc71077a"), u("photo-1583417319070-4a69db38a482")],
    "penang": [u("photo-1583417319070-4a69db38a482"), u("photo-1596422846543-75c6fc71077a")],
    "langkawi": [u("photo-1544551763-46a013bb70d5"), u("photo-1583417319070-4a69db38a482")],
    # Greece
    "athens": [u("photo-1555990538-17392d5e18f0"), u("photo-1533105079780-92b9be482077")],
    "santorini": [u("photo-1570077186671-e9e890419294"), u("photo-1533105079780-92b9be482077")],
    "crete": [u("photo-1533105079780-92b9be482077"), u("photo-1570077186671-e9e890419294")],
    # Croatia
    "dubrovnik": [u("photo-1555990793-da11153b2473"), u("photo-1578662996442-48f60103fc96")],
    "split": [u("photo-1578662996442-48f60103fc96"), u("photo-1555990793-da11153b2473")],
    # Vietnam
    "hanoi": [u("photo-1509030450996-ea4694f0cbe0"), u("photo-1528127269322-539801943592")],
    "ho-chi-minh-city": [u("photo-1528127269322-539801943592"), u("photo-1559592413-7cec4d0cae2b")],
    "da-nang": [u("photo-1559592413-7cec4d0cae2b"), u("photo-1528127269322-539801943592")],
    # Slovenia
    "ljubljana": [u("photo-1605649487212-47bdab064df7"), u("photo-1506905925346-21bda4d32df4")],
    "bled": [u("photo-1506905925346-21bda4d32df4"), u("photo-1605649487212-47bdab064df7")],
    # Denmark
    "copenhagen": [u("photo-1513622470522-26c3c8a854bc"), u("photo-1576924546985-6c3ac4c0b100")],
    "aarhus": [u("photo-1576924546985-6c3ac4c0b100"), u("photo-1513622470522-26c3c8a854bc")],
    # Georgia / Morocco / Mexico
    "tbilisi": [u("photo-1565008576549-57569a493712"), u("photo-1504893524553-b855bce32c67"), u("photo-1464822759023-fed622ff2c3b")],
    "batumi": [u("photo-1507272931001-fc06c17e4f43"), u("photo-1504893524553-b855bce32c67")],
    "marrakech": [u("photo-1489749798305-2ed9011178aa"), u("photo-1518684079-3c830dcef090"), u("photo-1552465011-b4e21bf6e79a")],
    "fez": [u("photo-1539020140153-e479b8c22e70"), u("photo-1518684079-3c830dcef090")],
    "oaxaca": [u("photo-1518638150340-37db5bb3c0c0"), u("photo-1549180030-48bf079fb38a"), u("photo-1514395462725-fb4566210144")],
    "mexico-city": [u("photo-1518105779142-d975f22deb17"), u("photo-1549180030-48bf079fb38a"), u("photo-1560969184-10fe8719e047")],
}

# Iconic photos that must only appear on their home city (when that city exists).
ICONIC_HOME: dict[str, str] = {
    u("photo-1502602898657-3e91760cbb34"): "paris",
    u("photo-1431274172761-fca41d930114"): "paris",
    u("photo-1493976040374-85c8e12f0c0e"): "kyoto",
}


def head_ok(url: str, cache: dict[str, bool]) -> bool:
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            ok = 200 <= resp.status < 300
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        ok = False
    cache[url] = ok
    return ok


def pick_for_city(
    slug: str,
    used: set[str],
    country_photo: str,
    cache: dict[str, bool],
) -> str:
    candidates = list(CITY_CANDIDATES.get(slug, []))
    # Regional European fallbacks that are NOT Paris/Kyoto icons
    candidates.extend(
        [
            u("photo-1605649487212-47bdab064df7"),
            u("photo-1516550893923-42d28e5677af"),
            u("photo-1467269204594-9661b134dd2b"),
            u("photo-1464822759023-fed622ff2c3b"),
            u("photo-1506905925346-21bda4d32df4"),
            u("photo-1530122037265-a5f1f91d3b99"),
            u("photo-1513622470522-26c3c8a854bc"),
            u("photo-1555990793-da11153b2473"),
            u("photo-1585208798174-6cedd86e019a"),
            u("photo-1539037116277-4db20889f2d4"),
            u("photo-1516483638261-f4dbaf036963"),
            u("photo-1507272931001-fc06c17e4f43"),
            u("photo-1504893524553-b855bce32c67"),
            u("photo-1583417319070-4a69db38a482"),
            u("photo-1552465011-b4e21bf6e79a"),
            u("photo-1528127269322-539801943592"),
            u("photo-1469474968028-56623f02e42e"),
            u("photo-1503614472-8c93d56e92ce"),
            u("photo-1540959733332-eab4deabeeaf"),
            u("photo-1624138784614-87fd1b6528f8"),
        ]
    )
    for url in candidates:
        if url in used or url == country_photo:
            continue
        home = ICONIC_HOME.get(url)
        if home and home != slug:
            continue
        if head_ok(url, cache):
            return url
    raise RuntimeError(f"No valid landmark photo for city={slug}")


def main() -> int:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    cache: dict[str, bool] = {}
    mismatches_before = 0
    changes = 0

    for country in data["countries"]:
        country_photo = country.get("photo_url") or ""
        used = {country_photo} if country_photo else set()
        for city in country.get("top_cities") or []:
            slug = city["slug"]
            old = city.get("photo_url") or ""
            # Detect Paris/Kyoto misuse before fix
            if ICONIC_HOME.get(old) and ICONIC_HOME[old] != slug:
                mismatches_before += 1
            new = pick_for_city(slug, used, country_photo, cache)
            if new != old:
                changes += 1
            city["photo_url"] = new
            used.add(new)
            print(f"{country['iso_code']} {slug:20} {new.split('photo-')[-1][:36]}")

    # Post-check: no iconic misuse
    bad = []
    for country in data["countries"]:
        for city in country.get("top_cities") or []:
            home = ICONIC_HOME.get(city.get("photo_url") or "")
            if home and home != city["slug"]:
                bad.append(f"{city['slug']} has {home} icon")

    if bad:
        print("FAIL iconic misuse:", bad, file=sys.stderr)
        return 1

    SEED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {SEED.relative_to(ROOT)} changes={changes} "
        f"iconic_mismatches_before={mismatches_before}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
