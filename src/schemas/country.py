"""Pydantic v2 schemas for country API responses."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Locale(str, Enum):
    EN = "en"
    ZH_HK = "zh-HK"
    JA = "ja"


class BestTravelSeasonOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    seasons: list[str]
    months: list[int]
    label: str


class TopCityOut(BaseModel):
    """Localized snapshot city for country browse cards (Phase 6.1)."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    name: str
    photo_url: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class CountryOut(BaseModel):
    """Localized country row returned by GET /api/v1/countries."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    iso_code: str = Field(..., min_length=2, max_length=2)
    slug: str | None = None
    name: str
    description: str
    safety_index: int = Field(..., ge=1, le=5)
    avg_daily_cost_usd: float = Field(..., gt=0)
    best_travel_season: BestTravelSeasonOut
    best_season: str = Field(
        default="",
        description="Localized best-season label derived from best_travel_season.",
    )
    region_tags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    top_cities: list[TopCityOut] = Field(default_factory=list)


def localize_i18n(value: dict[str, Any] | str, locale: Locale) -> str:
    if isinstance(value, str):
        return value
    key = locale.value
    text = value.get(key) or value.get(Locale.EN.value) or ""
    return str(text)


def top_cities_to_out(raw: Any, locale: Locale) -> list[TopCityOut]:
    if not isinstance(raw, list):
        return []
    out: list[TopCityOut] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if not slug:
            continue
        name_raw = item.get("name") or {}
        desc_raw = item.get("description") or {}
        tags = item.get("tags") or []
        out.append(
            TopCityOut(
                slug=str(slug),
                name=localize_i18n(
                    name_raw if isinstance(name_raw, dict) else str(name_raw), locale
                ),
                photo_url=item.get("photo_url"),
                description=localize_i18n(
                    desc_raw if isinstance(desc_raw, dict) else str(desc_raw or ""),
                    locale,
                ),
                tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            )
        )
    return out


def country_row_to_out(row: dict[str, Any], locale: Locale) -> CountryOut:
    season = row.get("best_travel_season") or {}
    label_raw = season.get("label", {})
    season_label = (
        localize_i18n(label_raw if isinstance(label_raw, dict) else {}, locale)
        if isinstance(label_raw, dict)
        else str(label_raw or "")
    )
    return CountryOut(
        id=row["id"],
        iso_code=row["iso_code"],
        slug=row.get("slug"),
        name=localize_i18n(row.get("name") or {}, locale),
        description=localize_i18n(row.get("description") or {}, locale),
        safety_index=int(row["safety_index"]),
        avg_daily_cost_usd=float(row["avg_daily_cost_usd"]),
        best_travel_season=BestTravelSeasonOut(
            seasons=list(season.get("seasons") or []),
            months=[int(m) for m in (season.get("months") or [])],
            label=season_label,
        ),
        best_season=season_label,
        region_tags=list(row.get("region_tags") or []),
        tags=list(row.get("tags") or []),
        photo_url=row.get("photo_url"),
        top_cities=top_cities_to_out(row.get("top_cities"), locale),
    )
