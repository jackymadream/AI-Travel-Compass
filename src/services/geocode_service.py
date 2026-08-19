"""Resolve place names and Google Maps URLs to coordinates (no Google API)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.utils.geo_parse import parse_google_maps_url

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GenAI-Travel-Compass/1.0 (geocode; https://travel.jackymadream.com)"
SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co/maps")


def looks_like_url(text: str) -> bool:
    raw = (text or "").strip().lower()
    return raw.startswith("http://") or raw.startswith("https://")


def is_short_maps_url(text: str) -> bool:
    raw = (text or "").strip().lower()
    return any(host in raw for host in SHORT_HOSTS)


def expand_maps_url(url: str, *, timeout: float = 8.0) -> str:
    """Follow redirects so goo.gl / maps.app links become parseable Maps URLs."""
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.head(url)
            if resp.status_code >= 400 or not str(resp.url):
                resp = client.get(url)
            return str(resp.url)
    except Exception as exc:  # noqa: BLE001
        logger.info("Maps URL expand failed: %s", exc)
        return url


def nominatim_search(
    query: str,
    *,
    city: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    q = (query or "").strip()
    if not q:
        return None
    if city and city.lower() not in q.lower():
        q = f"{q} {city}"
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(
                NOMINATIM_URL,
                params={"format": "json", "limit": 1, "q": q},
            )
            resp.raise_for_status()
            rows = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.info("Nominatim search failed: %s", exc)
        return None
    if not isinstance(rows, list) or not rows:
        return None
    hit = rows[0]
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "label": str(hit.get("display_name") or q),
    }


def resolve_place(
    *,
    query: str | None = None,
    name: str | None = None,
    city: str | None = None,
) -> dict[str, Any] | None:
    """
    Resolve a Maps URL or place name.

    Prefer explicit ``query`` (URL or typed place); fall back to ``name``.
    """
    primary = (query or "").strip() or (name or "").strip()
    if not primary:
        return None

    if looks_like_url(primary):
        expanded = expand_maps_url(primary) if is_short_maps_url(primary) else primary
        parsed = parse_google_maps_url(expanded)
        if parsed:
            lat, lon = parsed
            return {
                "lat": lat,
                "lon": lon,
                "label": (name or "").strip() or "Custom spot",
                "source": "maps_url",
            }
        geo = nominatim_search(expanded, city=city)
        if geo:
            geo["source"] = "nominatim"
            if (name or "").strip():
                geo["label"] = name.strip()
            return geo
        return None

    geo = nominatim_search(primary, city=city)
    if geo:
        geo["source"] = "nominatim"
        if (name or "").strip():
            geo["label"] = name.strip()
        return geo
    return None
