"""Curated signature POIs merged at ingest time (Approach A diversity)."""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any

from src.schemas.poi import PoiRecord

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SIGNATURE_PATH = ROOT_DIR / "data" / "city_signature_pois.json"
NEAR_DUPLICATE_METERS = 250.0


def poi_id_signature(city_slug: str, name: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"travel-compass:poi:signature:{city_slug.lower()}:{name.strip().lower()}",
        )
    )


def load_signature_payload(path: Path | None = None) -> dict[str, Any]:
    target = path or SIGNATURE_PATH
    if not target.is_file():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def signature_entries_for_city(
    city_slug: str,
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    payload = load_signature_payload(path)
    city = payload.get(city_slug.lower()) or {}
    if not isinstance(city, dict):
        return []
    pois = city.get("pois") or []
    return [p for p in pois if isinstance(p, dict) and str(p.get("name") or "").strip()]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def names_near_duplicate(a: str, b: str) -> bool:
    na = " ".join(a.lower().split())
    nb = " ".join(b.lower().split())
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False


def is_near_duplicate_poi(
    candidate: PoiRecord,
    existing: list[PoiRecord],
    *,
    meters: float = NEAR_DUPLICATE_METERS,
) -> bool:
    for other in existing:
        if names_near_duplicate(candidate.name, other.name):
            return True
        if (
            candidate.lat is not None
            and candidate.lon is not None
            and other.lat is not None
            and other.lon is not None
            and _haversine_m(candidate.lat, candidate.lon, other.lat, other.lon)
            <= meters
            and names_near_duplicate(candidate.name, other.name)
        ):
            return True
    return False


def build_signature_pois(
    *,
    city_slug: str,
    city_id: str,
    city_display: str,
    safety_score: int = 3,
    path: Path | None = None,
) -> list[PoiRecord]:
    """Convert curated JSON rows into ``PoiRecord`` with ``source=signature``."""
    out: list[PoiRecord] = []
    for raw in signature_entries_for_city(city_slug, path=path):
        name = str(raw.get("name") or "").strip()
        category = str(raw.get("category") or "attraction").strip().lower()
        if category not in {"attraction", "food", "rest"}:
            category = "attraction"
        tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()]
        neighborhood = str(raw.get("neighborhood") or "").strip()
        if neighborhood:
            tags = list(dict.fromkeys([*tags, f"neighborhood:{neighborhood}", neighborhood.lower()]))
        tags = list(dict.fromkeys([*tags, "signature", "popular"]))
        external = raw.get("external") if isinstance(raw.get("external"), dict) else {}
        wikidata = str(external.get("wikidata") or "").strip() or None
        if wikidata:
            tags = list(dict.fromkeys([*tags, f"wikidata:{wikidata}", "wikipedia"]))
        cost = float(raw.get("cost_usd") if raw.get("cost_usd") is not None else 0)
        duration = int(raw.get("duration_minutes") or 90)
        description = str(raw.get("description") or "").strip() or (
            f"Signature stop in {city_display}: {name}."
        )
        lat = raw.get("lat")
        lon = raw.get("lon")
        out.append(
            PoiRecord(
                id=poi_id_signature(city_slug, name),
                name=name,
                city=city_display,
                category=category,  # type: ignore[arg-type]
                description=description[:2000],
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                price_level=0 if cost <= 0 else (1 if cost < 15 else 2 if cost < 40 else 3),
                rating=4.5,
                safety_score=safety_score,
                city_id=city_id,
                tags=tags,
                cost_usd=cost,
                duration_minutes=duration,
                address=f"{neighborhood}, {city_display}" if neighborhood else city_display,
                source="signature",
                wikidata=wikidata,
            )
        )
    return out


def merge_signature_and_overpass(
    signatures: list[PoiRecord],
    overpass: list[PoiRecord],
) -> list[PoiRecord]:
    """Signatures first; drop Overpass rows that near-duplicate a signature."""
    merged = list(signatures)
    for poi in overpass:
        if is_near_duplicate_poi(poi, merged):
            continue
        merged.append(poi)
    return merged
