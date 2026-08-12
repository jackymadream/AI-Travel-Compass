"""Hybrid RAG search API — POST /api/v1/search (rate-limited)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.deps import SupabaseDep
from src.schemas.search import SearchRequest, SearchResponse
from src.services.rag_service import EmbeddingError, VectorSearchError
from src.services.rate_limit import SEARCH_RATE_LIMIT, limiter
from src.services.search_service import SearchService

router = APIRouter(tags=["search"])


def get_search_service(supabase: SupabaseDep) -> SearchService:
    """FastAPI dependency — overridable in tests."""
    return SearchService(supabase=supabase)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


@router.post("/search", response_model=SearchResponse)
@limiter.limit(SEARCH_RATE_LIMIT)
async def search_destinations(
    request: Request,
    response: Response,
    body: SearchRequest,
    service: SearchServiceDep,
) -> SearchResponse:
    """
    Hybrid search: SQL hard filters (budget / safety / tags) then
    Qdrant vector ranking scoped to the candidate set.

    Unauthenticated clients are limited to ``SEARCH_RATE_LIMIT`` (default 15/minute).
    """
    try:
        return await service.search(body)
    except (EmbeddingError, VectorSearchError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Search backend unavailable: {exc}",
        ) from exc
