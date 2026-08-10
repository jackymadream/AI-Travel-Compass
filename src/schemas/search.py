"""Pydantic v2 contracts for hybrid RAG search (Phase 2)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.country import Locale


class SearchRequest(BaseModel):
    """
    Hybrid search input.

    - ``query``: natural language (semantic + optional hard signals to extract).
    - Explicit ``max_budget`` / ``min_safety`` / ``tags`` are hard filters
      (CONTEXT.md); they must be applied in SQL before vector ranking.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language travel preference query.",
    )
    locale: Locale = Field(
        default=Locale.EN,
        description="Response + embedding locale preference (en, zh-HK, ja).",
    )
    max_budget: float | None = Field(
        default=None,
        gt=0,
        description="Hard filter: destination avg_daily_cost_usd <= max_budget (USD).",
    )
    min_safety: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Hard filter: destination safety_index >= min_safety.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Hard/soft tag hints (e.g. food, nature); used in SQL overlap and ranking.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max results to return after ranking.",
    )


class ExtractedIntent(BaseModel):
    """Result of intent decomposition (hard vs semantic)."""

    model_config = ConfigDict(extra="ignore")

    hard_filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured hard constraints applied in SQL.",
    )
    semantic_query: str = Field(
        default="",
        description="Residue text used for embedding / vector search.",
    )


class SearchHit(BaseModel):
    """Single ranked destination in the search response."""

    model_config = ConfigDict(extra="ignore")

    city_id: UUID | None = None
    country_id: UUID | None = None
    iso_code: str | None = Field(default=None, min_length=2, max_length=2)
    name: str
    description: str
    safety_index: int = Field(..., ge=1, le=5)
    avg_daily_cost_usd: float = Field(..., gt=0)
    tags: list[str] = Field(default_factory=list)
    score: float = Field(
        ...,
        description="Blended ranking score (higher is better).",
    )
    vector_score: float | None = Field(
        default=None,
        description="Raw Qdrant similarity when available.",
    )


class SearchResponse(BaseModel):
    """Hybrid search output."""

    model_config = ConfigDict(extra="ignore")

    query: str
    locale: Locale
    intent: ExtractedIntent | None = None
    candidate_count: int = Field(
        ...,
        ge=0,
        description="Size of SQL candidate set before vector ranking.",
    )
    empty_reason: str | None = Field(
        default=None,
        description="Set when no candidates (e.g. BUDGET_TOO_LOW, SAFETY_TOO_STRICT).",
    )
    results: list[SearchHit] = Field(default_factory=list)
