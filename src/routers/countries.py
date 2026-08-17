"""Countries API — deterministic listing with locale + hard filters."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from src.deps import SupabaseDep
from src.schemas.country import Locale, CountryOut, country_row_to_out

router = APIRouter(prefix="/countries", tags=["countries"])


def _parse_tags(tags: list[str] | None) -> list[str]:
    """Normalize repeated and comma-separated ``tags`` query values."""
    if not tags:
        return []
    out: list[str] = []
    for raw in tags:
        for part in str(raw).split(","):
            cleaned = part.strip().lower()
            if cleaned and cleaned not in out:
                out.append(cleaned)
    return out


@router.get("", response_model=list[CountryOut])
def list_countries(
    supabase: SupabaseDep,
    response: Response,
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
    tags: list[str] | None = Query(
        default=None,
        description=(
            "Soft browse filter: countries whose theme tags overlap "
            "(repeat param or comma-separated)."
        ),
    ),
) -> list[CountryOut]:
    """
    List active countries with multilingual fields and deterministic filters.

    Filters map to CONTEXT.md hard constraints:
      max_budget         → avg_daily_cost_usd
      min_safety_rating  → safety_index
    Phase 6.1:
      tags               → countries.tags overlap
    """
    # Browse photos/tags change with seed updates; never let browsers keep a
    # stale countries JSON that still points at deleted Unsplash assets.
    response.headers["Cache-Control"] = "no-store, max-age=0"

    tag_filter = _parse_tags(tags)

    query = (
        supabase.table("countries")
        .select(
            "id, iso_code, slug, name, description, safety_index, "
            "avg_daily_cost_usd, best_travel_season, region_tags, tags, "
            "photo_url, top_cities, is_active"
        )
        .eq("is_active", True)
    )

    if max_budget is not None:
        query = query.lte("avg_daily_cost_usd", max_budget)
    if min_safety_rating is not None:
        query = query.gte("safety_index", min_safety_rating)
    if tag_filter:
        # PostgREST: array overlaps (&&). Mock clients may implement .overlaps.
        query = query.overlaps("tags", tag_filter)

    query = query.order("iso_code")
    response = query.execute()
    rows = response.data or []

    return [country_row_to_out(row, locale) for row in rows]
