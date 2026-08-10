"""
Hybrid RAG search orchestration.

Flow (see docs/RAG_ARCHITECTURE.md):
  NL query → intent decomposition → Supabase SQL candidates
           → Qdrant vector search (scoped) → score ranking → SearchResponse
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from supabase import Client

from src.deps import get_supabase
from src.schemas.country import Locale, localize_i18n
from src.schemas.search import (
    ExtractedIntent,
    SearchHit,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger(__name__)

# Ranking blend: vector similarity dominates; tag overlap is a soft boost.
VECTOR_WEIGHT = 0.85
TAG_WEIGHT = 0.15


class SearchService:
    """Hybrid search: deterministic SQL candidates + RagService vector ranking."""

    def __init__(self, supabase: Client | None = None) -> None:
        self._supabase = supabase

    @property
    def supabase(self) -> Client:
        if self._supabase is None:
            self._supabase = get_supabase()
        return self._supabase

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Run the full hybrid pipeline."""
        intent = await self.extract_intent(request)
        hard_filters = self._merge_hard_filters(request, intent)
        semantic_query = intent.semantic_query or request.query
        locale = request.locale

        candidates = await self.sql_filter_candidates(hard_filters)
        if not candidates:
            return SearchResponse(
                query=request.query,
                locale=locale,
                intent=intent,
                candidate_count=0,
                empty_reason=self._empty_reason(hard_filters),
                results=[],
            )

        candidate_city_ids = self._candidate_ids(candidates)
        vector_hits = await self.vector_search(
            semantic_query=semantic_query,
            locale=locale.value,
            candidate_ids=candidate_city_ids,
            limit=max(request.limit * 3, request.limit),
        )

        ranked = await self.rank_results(
            candidates=candidates,
            vector_hits=vector_hits,
            tags=list(hard_filters.get("tags") or request.tags or []),
            locale=locale,
            limit=request.limit,
        )

        return SearchResponse(
            query=request.query,
            locale=locale,
            intent=intent,
            candidate_count=len(candidates),
            empty_reason=None,
            results=ranked,
        )

    async def extract_intent(self, request: SearchRequest) -> ExtractedIntent:
        """
        Decompose NL query into hard filters vs semantic residue.

        Stub: copies explicit request fields; later add LLM/rules extractor.
        """
        hard: dict[str, Any] = {}
        if request.max_budget is not None:
            hard["max_budget"] = request.max_budget
        if request.min_safety is not None:
            hard["min_safety"] = request.min_safety
        if request.tags:
            hard["tags"] = list(request.tags)

        return ExtractedIntent(
            hard_filters=hard,
            semantic_query=request.query.strip(),
        )

    async def sql_filter_candidates(
        self,
        hard_filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Deterministic Supabase filtering on cities (+ countries) → frozen set.

        Hard predicates:
          - cities.is_active / countries.is_active
          - avg_daily_cost_usd <= max_budget
          - safety_index >= min_safety
          - tags && request.tags (city tags) OR region_tags overlap
        """
        max_budget = hard_filters.get("max_budget")
        min_safety = hard_filters.get("min_safety")
        tags = [str(t).strip() for t in (hard_filters.get("tags") or []) if str(t).strip()]

        query = (
            self.supabase.table("cities")
            .select(
                "id, country_id, slug, name, description, safety_index, "
                "avg_daily_cost_usd, tags, is_active, "
                "countries!inner(id, iso_code, name, region_tags, is_active)"
            )
            .eq("is_active", True)
            .eq("countries.is_active", True)
        )

        if max_budget is not None:
            query = query.lte("avg_daily_cost_usd", float(max_budget))
        if min_safety is not None:
            query = query.gte("safety_index", int(min_safety))

        # Prefer DB-side overlap when tags are set; also keep a Python fallback
        # for region_tags after fetch if PostgREST overlaps-only on cities.tags.
        if tags:
            query = query.overlaps("tags", tags)

        query = query.order("avg_daily_cost_usd").order("id")
        response = query.execute()
        rows = response.data or []

        candidates: list[dict[str, Any]] = []
        for row in rows:
            country = row.get("countries") or {}
            if isinstance(country, list):
                country = country[0] if country else {}

            city_tags = _as_str_list(row.get("tags"))
            region_tags = _as_str_list(country.get("region_tags"))

            if tags:
                # Hard tag gate: city tags OR country region_tags must overlap.
                # overlaps() already applied on city tags; include region match
                # for rows that only match region (re-query path without city tags).
                if not (_overlaps(tags, city_tags) or _overlaps(tags, region_tags)):
                    continue

            candidates.append(
                {
                    "city_id": str(row["id"]),
                    "country_id": str(row["country_id"]),
                    "iso_code": country.get("iso_code"),
                    "slug": row.get("slug"),
                    "name": row.get("name") or {},
                    "description": row.get("description") or {},
                    "country_name": country.get("name") or {},
                    "safety_index": int(row["safety_index"]),
                    "avg_daily_cost_usd": float(row["avg_daily_cost_usd"]),
                    "tags": city_tags,
                    "region_tags": region_tags,
                }
            )

        # If tags were requested but city.tags overlap returned nothing,
        # fall back: budget/safety only, then require region_tags overlap in Python.
        if tags and not candidates:
            candidates = await self._sql_filter_by_region_tags(
                max_budget=max_budget,
                min_safety=min_safety,
                tags=tags,
            )

        logger.debug(
            "sql_filter_candidates filters=%s count=%d",
            hard_filters,
            len(candidates),
        )
        return candidates

    async def _sql_filter_by_region_tags(
        self,
        *,
        max_budget: Any,
        min_safety: Any,
        tags: list[str],
    ) -> list[dict[str, Any]]:
        """Fallback when only countries.region_tags overlap requested tags."""
        query = (
            self.supabase.table("cities")
            .select(
                "id, country_id, slug, name, description, safety_index, "
                "avg_daily_cost_usd, tags, is_active, "
                "countries!inner(id, iso_code, name, region_tags, is_active)"
            )
            .eq("is_active", True)
            .eq("countries.is_active", True)
        )
        if max_budget is not None:
            query = query.lte("avg_daily_cost_usd", float(max_budget))
        if min_safety is not None:
            query = query.gte("safety_index", int(min_safety))

        query = query.order("avg_daily_cost_usd").order("id")
        response = query.execute()
        rows = response.data or []

        out: list[dict[str, Any]] = []
        for row in rows:
            country = row.get("countries") or {}
            if isinstance(country, list):
                country = country[0] if country else {}
            city_tags = _as_str_list(row.get("tags"))
            region_tags = _as_str_list(country.get("region_tags"))
            if not (_overlaps(tags, city_tags) or _overlaps(tags, region_tags)):
                continue
            out.append(
                {
                    "city_id": str(row["id"]),
                    "country_id": str(row["country_id"]),
                    "iso_code": country.get("iso_code"),
                    "slug": row.get("slug"),
                    "name": row.get("name") or {},
                    "description": row.get("description") or {},
                    "country_name": country.get("name") or {},
                    "safety_index": int(row["safety_index"]),
                    "avg_daily_cost_usd": float(row["avg_daily_cost_usd"]),
                    "tags": city_tags,
                    "region_tags": region_tags,
                }
            )
        return out

    async def vector_search(
        self,
        *,
        semantic_query: str,
        locale: str,
        candidate_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        """
        Embed semantic_query and search Qdrant ``travel_destinations``.

        Scopes results to SQL candidate city IDs via RagService payload filter.
        """
        from src.services.rag_service import EmbeddingError, RagService, VectorSearchError

        if not candidate_ids:
            return []

        rag = RagService()
        try:
            hits = rag.search_by_query(
                text=semantic_query,
                candidate_ids=candidate_ids,
                limit=limit,
            )
        except (EmbeddingError, VectorSearchError) as exc:
            logger.exception("vector_search failed: %s", exc)
            raise

        by_city: dict[str, dict[str, Any]] = {}
        for hit in hits:
            row = {
                "city_id": hit.city_id,
                "country_id": hit.country_id,
                "score": hit.score,
                "vector_score": hit.score,
                "tags": hit.tags,
                "daily_budget": hit.daily_budget,
                "locale": hit.locale,
                "text": hit.text,
                "payload": hit.payload,
            }
            existing = by_city.get(hit.city_id)
            if existing is None:
                by_city[hit.city_id] = row
                continue
            existing_locale = existing.get("locale")
            if existing_locale != locale and hit.locale == locale:
                by_city[hit.city_id] = row
            elif existing_locale == locale:
                continue
            elif float(row["score"]) > float(existing["score"]):
                by_city[hit.city_id] = row

        return list(by_city.values())

    async def rank_results(
        self,
        *,
        candidates: list[dict[str, Any]],
        vector_hits: list[dict[str, Any]],
        tags: list[str],
        locale: Locale,
        limit: int,
    ) -> list[SearchHit]:
        """
        Blend vector similarity + tag overlap; emit localized SearchHit shortlist.

        Only SQL candidates may appear. If Qdrant returns nothing, fall back to
        tag/budget ordering within the candidate set.
        """
        by_id = {str(c["city_id"]): c for c in candidates}
        vector_by_id = {
            str(h["city_id"]): h for h in vector_hits if h.get("city_id")
        }

        scored: list[tuple[float, float, int, float, str]] = []
        # tuple: (-final, -vector, -safety, cost, city_id) for sort

        ids_to_rank = list(vector_by_id.keys()) if vector_by_id else list(by_id.keys())
        for city_id in ids_to_rank:
            candidate = by_id.get(city_id)
            if candidate is None:
                continue

            hit = vector_by_id.get(city_id)
            vector_score = float(hit["vector_score"]) if hit else 0.0
            city_tags = _as_str_list(candidate.get("tags"))
            region_tags = _as_str_list(candidate.get("region_tags"))
            all_tags = list(dict.fromkeys(city_tags + region_tags))
            matching = _intersection(tags, all_tags) if tags else []
            tag_score = (len(matching) / len(tags)) if tags else 0.0

            final = VECTOR_WEIGHT * vector_score + TAG_WEIGHT * tag_score
            safety = int(candidate["safety_index"])
            cost = float(candidate["avg_daily_cost_usd"])
            scored.append((-final, -vector_score, -safety, cost, city_id))

        scored.sort()
        results: list[SearchHit] = []
        for neg_final, neg_vector, _, _, city_id in scored[:limit]:
            candidate = by_id[city_id]
            hit = vector_by_id.get(city_id)
            city_tags = _as_str_list(candidate.get("tags"))
            region_tags = _as_str_list(candidate.get("region_tags"))
            all_tags = list(dict.fromkeys(city_tags + region_tags))
            matching = _intersection(tags, all_tags) if tags else all_tags

            results.append(
                SearchHit(
                    city_id=UUID(str(candidate["city_id"])),
                    country_id=UUID(str(candidate["country_id"])),
                    iso_code=candidate.get("iso_code"),
                    name=localize_i18n(candidate.get("name") or {}, locale),
                    description=localize_i18n(
                        candidate.get("description") or {}, locale
                    ),
                    safety_index=int(candidate["safety_index"]),
                    avg_daily_cost_usd=float(candidate["avg_daily_cost_usd"]),
                    tags=matching,
                    score=float(-neg_final),
                    vector_score=float(-neg_vector) if hit else None,
                )
            )
        return results

    def _merge_hard_filters(
        self,
        request: SearchRequest,
        intent: ExtractedIntent,
    ) -> dict[str, Any]:
        """Explicit request fields win over extracted intent values."""
        merged = dict(intent.hard_filters)
        if request.max_budget is not None:
            merged["max_budget"] = request.max_budget
        if request.min_safety is not None:
            merged["min_safety"] = request.min_safety
        if request.tags:
            merged["tags"] = list(request.tags)
        merged["locale"] = request.locale.value
        return merged

    def _candidate_ids(self, candidates: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        for row in candidates:
            for key in ("city_id", "id"):
                if key in row and row[key] is not None:
                    ids.append(str(row[key]))
                    break
        return ids

    def _empty_reason(self, hard_filters: dict[str, Any]) -> str:
        if hard_filters.get("tags") and (
            "max_budget" in hard_filters or "min_safety" in hard_filters
        ):
            return "NO_CANDIDATES"
        if "max_budget" in hard_filters and "min_safety" in hard_filters:
            return "NO_CANDIDATES"
        if "max_budget" in hard_filters:
            return "BUDGET_TOO_LOW"
        if "min_safety" in hard_filters:
            return "SAFETY_TOO_STRICT"
        if hard_filters.get("tags"):
            return "NO_TAG_MATCH"
        return "NO_CANDIDATES"


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _overlaps(a: list[str], b: list[str]) -> bool:
    left = {x.lower() for x in a}
    right = {x.lower() for x in b}
    return bool(left & right)


def _intersection(requested: list[str], available: list[str]) -> list[str]:
    available_map = {x.lower(): x for x in available}
    out: list[str] = []
    for tag in requested:
        key = tag.lower()
        if key in available_map:
            out.append(available_map[key])
    return out
