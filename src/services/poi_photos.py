"""Ingest-time POI photo resolution: Wikidata / Wikipedia / Places. No generate-time search."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import quote

from src.services.itinerary_eval import is_denied_stock_photo, photo_id_from_url
from src.services.itinerary_i18n import (
    all_stock_photo_urls,
    photo_candidates,
    photo_shape,
)

logger = logging.getLogger(__name__)

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_OPENSEARCH = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=800"
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_MEDIA = "https://places.googleapis.com/v1/{name}/media"
WIKI_USER_AGENT = (
    "GenAITravelCompass/1.0 (itinerary POI photos; https://github.com/)"
)
WIKI_TIMEOUT_S = 3.0
PLACES_TIMEOUT_S = 8.0
MAX_WIKI_DISTANCE_KM = 25.0
MAX_PLACES_DISTANCE_KM = 0.5

WikiFetch = Callable[[str, dict[str, str] | None], dict[str, Any] | list[Any] | None]
PhotoSource = str  # wikidata | wikipedia | places | cuisine_seed | none

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


@dataclass(frozen=True)
class PhotoHit:
    url: str | None
    source: PhotoSource
    confidence: str  # high | medium | low
    google_place_name: str | None = None
    google_photo_name: str | None = None


def resolve_grounded_photo(
    name: str,
    *,
    city: str | None = None,
    wikidata: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tags: Iterable[str] | None = None,
    fetch: WikiFetch | None = None,
) -> PhotoHit:
    """
    Fail-closed Wikipedia/Wikidata lookup for ingest.

    Does not fall back to Unsplash stock. Callers persist ``source=none``
    when ``url`` is None.
    """
    qid = wikidata or _wikidata_from_tags(tags)
    getter = fetch or _http_get_json
    if qid:
        wiki = _wikidata_p18(qid, lat=lat, lon=lon, fetch=getter)
        if wiki and persistable_photo_url(wiki):
            return PhotoHit(url=wiki, source="wikidata", confidence="high")
    thumb = _wikipedia_thumbnail(name, city, lat=lat, lon=lon, fetch=getter)
    if thumb and persistable_photo_url(thumb):
        return PhotoHit(url=thumb, source="wikipedia", confidence="medium")
    commons = _commons_thumbnail(name, city, lat=lat, lon=lon, fetch=getter)
    if commons and persistable_photo_url(commons):
        return PhotoHit(url=commons, source="wikipedia", confidence="medium")
    return PhotoHit(url=None, source="none", confidence="low")


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
    """Ingest helper: grounded URL or empty string (never category stock)."""
    del category, used_urls
    hit = resolve_grounded_photo(
        name,
        city=city,
        wikidata=wikidata,
        lat=lat,
        lon=lon,
        tags=tags,
        fetch=fetch,
    )
    return hit.url or ""


def resolve_places_photo(
    name: str,
    *,
    city: str | None,
    lat: float | None,
    lon: float | None,
    api_key: str,
    google_place_name: str | None = None,
    google_photo_name: str | None = None,
    client: Any | None = None,
) -> PhotoHit:
    """Google Places photo when the matched venue is within 500 m of OSM coords."""
    key = (api_key or "").strip()
    if not key or not (name or "").strip():
        return PhotoHit(url=None, source="none", confidence="low")
    try:
        import httpx
    except ImportError:
        return PhotoHit(url=None, source="none", confidence="low")

    own_client = client is None
    http = client or httpx.Client(timeout=PLACES_TIMEOUT_S, follow_redirects=True)
    try:
        photo_name = str(google_photo_name or "").strip()
        place_name = str(google_place_name or "").strip() or None
        if photo_name:
            stored = _places_media_photo(photo_name, key=key, client=http)
            if stored:
                return PhotoHit(
                    url=stored,
                    source="places",
                    confidence="high",
                    google_place_name=place_name,
                    google_photo_name=photo_name,
                )
        body: dict[str, Any] = {
            "textQuery": f"{name} {city or ''}".strip(),
            "pageSize": 1,
        }
        if lat is not None and lon is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": 500.0,
                }
            }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": (
                "places.name,places.photos,places.location,"
                "places.displayName,places.formattedAddress"
            ),
        }
        resp = http.post(PLACES_SEARCH_URL, json=body, headers=headers)
        if resp.status_code >= 400:
            logger.info("Places photo search HTTP %s for %s", resp.status_code, name[:80])
            return PhotoHit(url=None, source="none", confidence="low")
        places = (resp.json() or {}).get("places") or []
        if not places:
            return PhotoHit(url=None, source="none", confidence="low")
        place = places[0]
        loc = place.get("location") or {}
        plat, plon = loc.get("latitude"), loc.get("longitude")
        if lat is not None and lon is not None and plat is not None and plon is not None:
            try:
                dist = _haversine_km(float(lat), float(lon), float(plat), float(plon))
                if dist > MAX_PLACES_DISTANCE_KM:
                    return PhotoHit(url=None, source="none", confidence="low")
            except (TypeError, ValueError):
                return PhotoHit(url=None, source="none", confidence="low")
        photos = place.get("photos") or []
        if not photos:
            return PhotoHit(url=None, source="none", confidence="low")
        photo_name = str(photos[0].get("name") or "").strip()
        if not photo_name:
            return PhotoHit(url=None, source="none", confidence="low")
        place_name = str(place.get("name") or "").strip() or None
        stored = _places_media_photo(photo_name, key=key, client=http)
        if stored:
            return PhotoHit(
                url=stored,
                source="places",
                confidence="high",
                google_place_name=place_name,
                google_photo_name=photo_name,
            )
        return PhotoHit(url=None, source="none", confidence="low")
    except Exception as exc:  # noqa: BLE001
        logger.info("Places photo lookup failed for %s: %s", name[:80], exc)
        return PhotoHit(url=None, source="none", confidence="low")
    finally:
        if own_client:
            http.close()


def persistable_photo_url(url: str | None) -> str | None:
    """HTTPS image URL safe to copy onto an itinerary activity."""
    text = (url or "").strip()
    if not text.startswith("https://"):
        return None
    if is_allowed_photo_url(text):
        return text
    return None


def unique_stock_photo(
    name: str,
    *,
    category: str = "attraction",
    city: str | None = None,
    iso: str | None = None,
    used_urls: set[str] | None = None,
) -> str:
    """Allowlisted Unsplash for cuisine seeds / UI placeholders — not POI identity."""
    used = used_urls or set()
    shape = photo_shape(name, category)
    local: list[str] = []
    seen: set[str] = set()
    for key in (shape, category, "park", "rest", "worship", "attraction"):
        for url in photo_candidates(key, city=city, iso=iso, poi_name=name):
            if url and url not in seen:
                seen.add(url)
                local.append(url)
    hit = _first_unused_stock(name, local, used)
    if hit:
        return hit
    global_urls = [u for u in all_stock_photo_urls() if u not in seen]
    return _first_unused_stock(name, global_urls, used) or ""


def _first_unused_stock(name: str, urls: list[str], used: set[str]) -> str:
    candidates = [u for u in urls if is_allowed_photo_url(u) and not is_denied_stock_photo(u)]
    if not candidates:
        return ""
    start = int(hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest(), 16) % len(
        candidates
    )
    for i in range(len(candidates)):
        url = candidates[(start + i) % len(candidates)]
        if url not in used:
            return url
    return ""


def is_allowed_photo_url(url: str | None) -> bool:
    text = (url or "").strip()
    if not text.startswith("https://"):
        return False
    lower = text.lower()
    if lower.endswith(".svg"):
        return False
    if "upload.wikimedia.org" in lower or "commons.wikimedia.org" in lower:
        return True
    if "googleusercontent.com" in lower:
        return True
    if "images.unsplash.com" in lower:
        pid = photo_id_from_url(text)
        return bool(pid) and pid in _unsplash_allowlist() and not is_denied_stock_photo(text)
    return False


def titles_related(
    poi_name: str,
    wiki_title: str,
    *,
    require_all_tokens: bool = False,
) -> bool:
    """True when Wikipedia title shares meaningful tokens with the POI name."""
    poi = (poi_name or "").strip()
    title = (wiki_title or "").strip()
    if not poi or not title:
        return False
    if poi.lower() in title.lower() or title.lower() in poi.lower():
        return True
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
    if require_all_tokens:
        return poi_toks <= title_toks
    return len(overlap) >= 2


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


def _wikidata_p18(
    qid: str,
    *,
    lat: float | None,
    lon: float | None,
    fetch: WikiFetch | None,
) -> str | None:
    getter = fetch or _http_get_json
    data = getter(WIKIDATA_ENTITY.format(qid=qid), None)
    if not isinstance(data, dict):
        return None
    entities = data.get("entities") or {}
    entity = entities.get(qid) or entities.get(qid.upper()) or {}
    claims = entity.get("claims") or {}
    has_poi_coords = lat is not None and lon is not None
    if has_poi_coords:
        wlat, wlon = _wikidata_p625(claims)
        if wlat is None or wlon is None:
            return None
        try:
            if _haversine_km(float(lat), float(lon), float(wlat), float(wlon)) > MAX_WIKI_DISTANCE_KM:
                return None
        except (TypeError, ValueError):
            return None
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


def _wikidata_p625(claims: dict[str, Any]) -> tuple[float | None, float | None]:
    p625 = claims.get("P625") or []
    if not p625:
        return None, None
    try:
        value = p625[0]["mainsnak"]["datavalue"]["value"]
        return float(value["latitude"]), float(value["longitude"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None, None


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
    queries: list[str] = []
    if city_s:
        queries.append(f"{city_s} {title}")
    queries.append(title)
    for query in queries:
        if not query.strip():
            continue
        thumb = _summary_thumbnail(query, getter, poi_name=title, lat=lat, lon=lon)
        if thumb:
            return thumb
    if city_s:
        hit = _opensearch_title(f"{city_s} {title}", getter)
        if hit:
            return _summary_thumbnail(hit, getter, poi_name=title, lat=lat, lon=lon)
        hit = _opensearch_title(title, getter)
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
    has_poi_coords = lat is not None and lon is not None
    if not titles_related(poi_name, wiki_title, require_all_tokens=not has_poi_coords):
        return None
    coords = data.get("coordinates") or {}
    if has_poi_coords:
        if not isinstance(coords, dict):
            return None
        wlat = coords.get("lat")
        wlon = coords.get("lon")
        if wlat is None or wlon is None:
            return None
        try:
            if _haversine_km(float(lat), float(lon), float(wlat), float(wlon)) > MAX_WIKI_DISTANCE_KM:
                return None
        except (TypeError, ValueError):
            return None
    orig = data.get("originalimage") if isinstance(data.get("originalimage"), dict) else {}
    thumb = data.get("thumbnail") if isinstance(data.get("thumbnail"), dict) else {}
    for blob in (orig, thumb):
        src = blob.get("source") if blob else None
        if isinstance(src, str) and persistable_photo_url(src):
            return src
    return None


def _commons_thumbnail(
    name: str,
    city: str | None,
    *,
    lat: float | None,
    lon: float | None,
    fetch: WikiFetch | None = None,
) -> str | None:
    title = (name or "").strip()
    if not title:
        return None
    getter = fetch or _http_get_json
    queries: list[str] = []
    city_s = (city or "").strip()
    if city_s:
        queries.append(f'{title} {city_s}')
    queries.append(title)
    require_all_tokens = lat is None or lon is None
    for query in queries:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": "3",
            "prop": "imageinfo|coordinates",
            "iiprop": "url",
            "iiurlwidth": "800",
            "format": "json",
        }
        data = getter(COMMONS_API, params)
        if not isinstance(data, dict):
            continue
        pages = (data.get("query") or {}).get("pages") or {}
        if not isinstance(pages, dict):
            continue
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            raw_title = str(page.get("title") or "")
            file_title = raw_title.replace("File:", "").replace("_", " ").strip()
            if not titles_related(title, file_title, require_all_tokens=require_all_tokens):
                continue
            if lat is not None and lon is not None:
                coords = page.get("coordinates") or []
                if not isinstance(coords, list) or not coords:
                    continue
                coord = coords[0] if isinstance(coords[0], dict) else {}
                clat = coord.get("lat")
                clon = coord.get("lon")
                if clat is None or clon is None:
                    continue
                try:
                    if _haversine_km(float(lat), float(lon), float(clat), float(clon)) > MAX_WIKI_DISTANCE_KM:
                        continue
                except (TypeError, ValueError):
                    continue
            infos = page.get("imageinfo") or []
            if not isinstance(infos, list):
                continue
            for info in infos:
                src = info.get("thumburl") or info.get("url")
                if isinstance(src, str) and persistable_photo_url(src):
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


def _places_media_photo(photo_name: str, *, key: str, client: Any) -> str | None:
    name = (photo_name or "").strip()
    if not name:
        return None
    media_url = PLACES_MEDIA.format(name=name)
    media = client.get(
        media_url,
        params={"maxHeightPx": 800, "skipHttpRedirect": "true", "key": key},
    )
    if media.status_code >= 400:
        return None
    payload: Any = {}
    ctype = media.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        payload = media.json()
    uri = ""
    if isinstance(payload, dict):
        uri = str(payload.get("photoUri") or "")
    if not uri and str(media.url).startswith("https://"):
        uri = str(media.url)
    return persistable_photo_url(uri)


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
