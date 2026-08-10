"""Countries API — deterministic listing with locale + hard filters."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.deps import SupabaseDep
from src.schemas.country import Locale, CountryOut, country_row_to_out

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[CountryOut])
def list_countries(
    supabase: SupabaseDep,
    locale: Locale = Query(
        default=Locale.EN,
        description="Response language for name/description (en, zh-HK, ja).",
    ),
    max_budget: float | None = Query(
        default=None,
        gt=0,
        description="Hard filter: avg_daily_cost_usd <= max_budget (USD).",
    ),
    min_safety_rating: int | None = Query(
        default=None,
        ge=1,
        le=5,
        description="Hard filter: safety_index >= min_safety_rating (1–5).",
    ),
) -> list[CountryOut]:
    """
    List active countries with multilingual fields and deterministic filters.

    Filters map to CONTEXT.md hard constraints:
      max_budget         → avg_daily_cost_usd
      min_safety_rating  → safety_index
    """
    query = (
        supabase.table("countries")
        .select(
            "id, iso_code, name, description, safety_index, "
            "avg_daily_cost_usd, best_travel_season, region_tags, is_active"
        )
        .eq("is_active", True)
    )

    if max_budget is not None:
        query = query.lte("avg_daily_cost_usd", max_budget)
    if min_safety_rating is not None:
        query = query.gte("safety_index", min_safety_rating)

    query = query.order("iso_code")
    response = query.execute()
    rows = response.data or []

    return [country_row_to_out(row, locale) for row in rows]
