"""Hybrid RAG search API — POST /api/v1/search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from src.deps import SupabaseDep
from src.schemas.search import SearchRequest, SearchResponse
from src.services.rag_service import EmbeddingError, VectorSearchError
from src.services.search_service import SearchService

router = APIRouter(tags=["search"])


def get_search_service(supabase: SupabaseDep) -> SearchService:
    """FastAPI dependency — overridable in tests."""
    return SearchService(supabase=supabase)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


@router.post("/search", response_model=SearchResponse)
async def search_destinations(
    body: SearchRequest,
    service: SearchServiceDep,
) -> SearchResponse:
    """
    Hybrid search: SQL hard filters (budget / safety / tags) then
    Qdrant vector ranking scoped to the candidate set.
    """
    try:
        return await service.search(body)
    except (EmbeddingError, VectorSearchError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Search backend unavailable: {exc}",
        ) from exc
