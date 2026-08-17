"""Resolve itinerary POI photos: Wikidata/Wikipedia, then unique city stock."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Any, Callable, Iterable
from urllib.parse import quote

from src.services.cache_service import TTL_POI_SECONDS, get_cache_service, make_cache_key
from src.services.itinerary_eval import photo_id_from_url
from src.services.itinerary_i18n import (
    category_photo,
    photo_candidates,
    photo_shape,
)

logger = logging.getLogger(__name__)

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_OPENSEARCH = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=800"
WIKI_USER_AGENT = (
    "GenAITravelCompass/1.0 (itinerary POI photos; https://github.com/)"
)
WIKI_TIMEOUT_S = 3.0
MAX_WIKI_DISTANCE_KM = 25.0

WikiFetch = Callable[[str, dict[str, str] | None], dict[str, Any] | list[Any] | None]

_STOPWORDS = {
    "the",
    "and",
    "for",
    "of",
    "in",
    "at",
    "to",
    "a",
    "an",
    "branch",
    "center",
    "centre",
}


def resolve_poi_photo(
    name: str,
    *,
    city: str | None = None,
    category: str = "attraction",
    used_urls: set[str] | None = None,
    fetch: WikiFetch | None = None,
    wikidata: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tags: Iterable[str] | None = None,
) -> str:
    """
    Return a loadable photo URL for ``name``.

    Prefers Wikidata P18, then a Wikipedia thumbnail whose title matches the
    POI; falls back to category-shaped Unsplash stock.
    """
    used = used_urls if used_urls is not None else set()
    qid = wikidata or _wikidata_from_tags(tags)
    wiki = None
    if fetch is not None or not os.getenv("PYTEST_CURRENT_TEST"):
        wiki = _cached_related_photo(
            name,
            city,
            qid=qid,
            lat=lat,
            lon=lon,
            fetch=fetch,
        )
    if wiki and is_allowed_photo_url(wiki):
        return wiki
    return unique_stock_photo(
        name,
        category=category,
        city=city,
        used_urls=used,
    )


def unique_stock_photo(
    name: str,
    *,
    category: str = "attraction",
    city: str | None = None,
    iso: str | None = None,
    used_urls: set[str] | None = None,
) -> str:
    """City/category Unsplash pool, indexed by ``name``, skipping used URLs."""
    used = used_urls or set()
    shape = photo_shape(name, category)
    candidates = photo_candidates(shape, city=city, iso=iso, poi_name=name)
    if not candidates:
        candidates = photo_candidates(category, city=city, iso=iso, poi_name=name)
    candidates = [u for u in candidates if is_allowed_photo_url(u)]
    if not candidates:
        fallback = category_photo(category, 0, city=city, iso=iso, poi_name=name)
        return fallback if is_allowed_photo_url(fallback) else fallback
    start = int(hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest(), 16) % len(
        candidates
    )
    for i in range(len(candidates)):
        url = candidates[(start + i) % len(candidates)]
        if url not in used:
            return url
    return candidates[start]


def is_allowed_photo_url(url: str | None) -> bool:
    text = (url or "").strip()
    if not text.startswith("https://"):
        return False
    lower = text.lower()
    if lower.endswith(".svg"):
        return False
    if "upload.wikimedia.org" in lower or "commons.wikimedia.org" in lower:
        return True
    if "images.unsplash.com" in lower:
        pid = photo_id_from_url(text)
        return bool(pid) and pid in _unsplash_allowlist()
    return False


def titles_related(poi_name: str, wiki_title: str) -> bool:
    """True when Wikipedia title shares meaningful tokens with the POI name."""
    poi = (poi_name or "").strip()
    title = (wiki_title or "").strip()
    if not poi or not title:
        return False
    cjk_poi = re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]{2,}", poi)
    if cjk_poi and any(tok in title for tok in cjk_poi):
        return True
    poi_toks = _tokens(poi)
    title_toks = _tokens(title)
    if not poi_toks:
        return False
    overlap = poi_toks & title_toks
    if not overlap:
        return False
    return len(overlap) >= 1 and (len(overlap) >= 2 or len(poi_toks) <= 2)


def _tokens(text: str) -> set[str]:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return {p for p in parts if len(p) > 2 and p not in _STOPWORDS}


def _wikidata_from_tags(tags: Iterable[str] | None) -> str | None:
    for tag in tags or []:
        raw = str(tag)
        if raw.lower().startswith("wikidata:"):
            qid = raw.split(":", 1)[1].strip()
            if re.fullmatch(r"Q\d+", qid, flags=re.IGNORECASE):
                return qid.upper()
        if re.fullmatch(r"Q\d+", raw, flags=re.IGNORECASE):
            return raw.upper()
    return None


def _unsplash_allowlist() -> set[str]:
    from src.services.itinerary_i18n import unsplash_allowlist

    return unsplash_allowlist()


def _cached_related_photo(
    name: str,
    city: str | None,
    *,
    qid: str | None,
    lat: float | None,
    lon: float | None,
    fetch: WikiFetch | None,
) -> str | None:
    key = make_cache_key("photo:wiki", name, city or "", qid or "")
    cache = get_cache_service()
    cached = cache.get(key)
    if cached == "":
        return None
    if isinstance(cached, str) and cached.startswith("http"):
        return cached if is_allowed_photo_url(cached) else None
    url = None
    if qid:
        url = _wikidata_p18(qid, fetch=fetch)
    if not url:
        url = _wikipedia_thumbnail(name, city, lat=lat, lon=lon, fetch=fetch)
    cache.set(key, url or "", ttl_seconds=TTL_POI_SECONDS)
    return url


def _wikidata_p18(qid: str, *, fetch: WikiFetch | None) -> str | None:
    getter = fetch or _http_get_json
    data = getter(WIKIDATA_ENTITY.format(qid=qid), None)
    if not isinstance(data, dict):
        return None
    entities = data.get("entities") or {}
    entity = entities.get(qid) or entities.get(qid.upper()) or {}
    claims = entity.get("claims") or {}
    p18 = claims.get("P18") or []
    if not p18:
        return None
    try:
        filename = p18[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(filename, str) or not filename.strip():
        return None
    if filename.lower().endswith(".svg"):
        return None
    return COMMONS_FILE.format(name=quote(filename.replace(" ", "_"), safe=""))


def _wikipedia_thumbnail(
    name: str,
    city: str | None,
    *,
    lat: float | None = None,
    lon: float | None = None,
    fetch: WikiFetch | None = None,
) -> str | None:
    title = (name or "").strip()
    if not title:
        return None
    city_s = (city or "").strip()
    getter = fetch or _http_get_json
    for query in (title, f"{title} {city_s}".strip() if city_s else ""):
        if not query:
            continue
        thumb = _summary_thumbnail(query, getter, poi_name=title, lat=lat, lon=lon)
        if thumb:
            return thumb
    if city_s:
        hit = _opensearch_title(f"{title} {city_s}", getter)
        if hit:
            return _summary_thumbnail(hit, getter, poi_name=title, lat=lat, lon=lon)
    return None


def _summary_thumbnail(
    title: str,
    getter: WikiFetch,
    *,
    poi_name: str,
    lat: float | None,
    lon: float | None,
) -> str | None:
    path_title = quote(title.replace(" ", "_"), safe="")
    url = WIKI_SUMMARY.format(title=path_title)
    data = getter(url, None)
    if not isinstance(data, dict):
        return None
    if str(data.get("type") or "") == "disambiguation":
        return None
    wiki_title = str(data.get("title") or title)
    if not titles_related(poi_name, wiki_title):
        return None
    coords = data.get("coordinates") or {}
    if lat is not None and lon is not None and isinstance(coords, dict):
        wlat = coords.get("lat")
        wlon = coords.get("lon")
        try:
            if wlat is not None and wlon is not None:
                if _haversine_km(float(lat), float(lon), float(wlat), float(wlon)) > MAX_WIKI_DISTANCE_KM:
                    return None
        except (TypeError, ValueError):
            pass
    orig = data.get("originalimage") if isinstance(data.get("originalimage"), dict) else {}
    thumb = data.get("thumbnail") if isinstance(data.get("thumbnail"), dict) else {}
    for blob in (orig, thumb):
        src = blob.get("source") if blob else None
        if isinstance(src, str) and is_allowed_photo_url(src):
            return src
    return None


def _opensearch_title(query: str, getter: WikiFetch) -> str | None:
    url = (
        f"{WIKI_OPENSEARCH}?action=opensearch&search={quote(query)}"
        "&limit=1&namespace=0&format=json"
    )
    data = getter(url, None)
    if not isinstance(data, list) or len(data) < 2:
        return None
    titles = data[1]
    if isinstance(titles, list) and titles and isinstance(titles[0], str):
        return titles[0]
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _http_get_json(
    url: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any] | list[Any] | None:
    try:
        import httpx

        headers = {
            "User-Agent": WIKI_USER_AGENT,
            "Accept": "application/json",
        }
        with httpx.Client(timeout=WIKI_TIMEOUT_S, headers=headers, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.info("Wikipedia photo lookup failed for %s: %s", url[:80], exc)
        return None
