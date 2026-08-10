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


class CountryOut(BaseModel):
    """Localized country row returned by GET /api/v1/countries."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    iso_code: str = Field(..., min_length=2, max_length=2)
    name: str
    description: str
    safety_index: int = Field(..., ge=1, le=5)
    avg_daily_cost_usd: float = Field(..., gt=0)
    best_travel_season: BestTravelSeasonOut
    region_tags: list[str] = Field(default_factory=list)


def localize_i18n(value: dict[str, Any] | str, locale: Locale) -> str:
    if isinstance(value, str):
        return value
    key = locale.value
    text = value.get(key) or value.get(Locale.EN.value) or ""
    return str(text)


def country_row_to_out(row: dict[str, Any], locale: Locale) -> CountryOut:
    season = row.get("best_travel_season") or {}
    label_raw = season.get("label", {})
    return CountryOut(
        id=row["id"],
        iso_code=row["iso_code"],
        name=localize_i18n(row.get("name") or {}, locale),
        description=localize_i18n(row.get("description") or {}, locale),
        safety_index=int(row["safety_index"]),
        avg_daily_cost_usd=float(row["avg_daily_cost_usd"]),
        best_travel_season=BestTravelSeasonOut(
            seasons=list(season.get("seasons") or []),
            months=[int(m) for m in (season.get("months") or [])],
            label=localize_i18n(label_raw if isinstance(label_raw, dict) else {}, locale)
            if isinstance(label_raw, dict)
            else str(label_raw or ""),
        ),
        region_tags=list(row.get("region_tags") or []),
    )
