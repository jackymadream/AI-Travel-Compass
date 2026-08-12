"""Cities listing for planner UI (Phase 5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from src.deps import SupabaseDep

router = APIRouter(prefix="/cities", tags=["cities"])


class CitySummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    slug: str
    name: str
    country_iso: str | None = None
    safety_index: int | None = None
    avg_daily_cost_usd: float | None = None
    tags: list[str] = Field(default_factory=list)


@router.get("", response_model=list[CitySummary])
async def list_cities(
    supabase: SupabaseDep,
    locale: str = Query(default="en"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CitySummary]:
    """Active cities with localized display names (for planner city picker)."""
    cities = (
        supabase.table("cities")
        .select(
            "id, slug, name, safety_index, avg_daily_cost_usd, tags, country_id, is_active"
        )
        .eq("is_active", True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    countries = (
        supabase.table("countries").select("id, iso_code").execute().data or []
    )
    iso_by_id = {c["id"]: c["iso_code"] for c in countries}

    results: list[CitySummary] = []
    for row in cities:
        name_obj = row.get("name") or {}
        if isinstance(name_obj, dict):
            label = (
                name_obj.get(locale)
                or name_obj.get("en")
                or row.get("slug")
                or "City"
            )
        else:
            label = str(name_obj)
        tags = row.get("tags") or []
        results.append(
            CitySummary(
                id=str(row["id"]),
                slug=str(row["slug"]),
                name=str(label),
                country_iso=iso_by_id.get(row.get("country_id")),
                safety_index=row.get("safety_index"),
                avg_daily_cost_usd=float(row["avg_daily_cost_usd"])
                if row.get("avg_daily_cost_usd") is not None
                else None,
                tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            )
        )
    results.sort(key=lambda c: c.name.lower())
    return results
