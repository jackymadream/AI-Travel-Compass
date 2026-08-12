"""Itinerary generation + saved itinerary CRUD (Phase 3 / 5.3)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from src.deps import SupabaseDep
from src.deps_auth import CurrentUserDep
from src.schemas.itinerary import ItineraryRequest, ItineraryResponse
from src.schemas.saved_itinerary import (
    SavedItinerary,
    SavedItineraryList,
    SaveFromGenerateRequest,
    SaveItineraryRequest,
)
from src.services.agent_service import AgentPlanningError, AgentService
from src.services.agent_tools import search_pois_tool
from src.services.llm import try_get_llm_service

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


def get_agent_service() -> AgentService:
    """FastAPI dependency — live POI search (mock fallback) + optional Gemini."""
    llm = try_get_llm_service()
    return AgentService(
        llm_client=llm,
        search_pois=search_pois_tool,
    )


AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]


@router.post("/generate", response_model=ItineraryResponse)
async def generate_itinerary(
    body: ItineraryRequest,
    service: AgentServiceDep,
) -> ItineraryResponse:
    """
    Tool-calling itinerary agent: retrieve POIs, draft + evaluate schedule
    (max retry turns), return validated ``ItineraryResponse``.
    """
    try:
        return await service.plan_itinerary(body)
    except AgentPlanningError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "violations": exc.violations,
            },
        ) from exc


def _days_payload(days_data: Any) -> Any:
    if hasattr(days_data, "model_dump"):
        return days_data.model_dump(mode="json")
    if isinstance(days_data, list):
        return [
            d.model_dump(mode="json") if hasattr(d, "model_dump") else d
            for d in days_data
        ]
    return days_data


def _row_to_saved(row: dict[str, Any]) -> SavedItinerary:
    return SavedItinerary.model_validate(row)


@router.post("", response_model=SavedItinerary, status_code=status.HTTP_201_CREATED)
async def save_itinerary(
    body: SaveItineraryRequest,
    user: CurrentUserDep,
    supabase: SupabaseDep,
) -> SavedItinerary:
    """Persist a generated plan for the authenticated user."""
    row = {
        "user_id": user.id,
        "title": body.title,
        "destination": body.destination,
        "city_id": str(body.city_id) if body.city_id else None,
        "days_data": _days_payload(body.days_data),
        "total_cost_usd": body.total_cost_usd,
        "agent_reasoning": body.agent_reasoning,
    }
    try:
        result = supabase.table("user_itineraries").insert(row).execute()
        data = (result.data or [None])[0]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save itinerary: {exc}",
        ) from exc
    if not data:
        raise HTTPException(status_code=500, detail="Insert returned no row")
    return _row_to_saved(data)


@router.post("/save", response_model=SavedItinerary, status_code=status.HTTP_201_CREATED)
async def save_generated_itinerary(
    body: SaveFromGenerateRequest,
    user: CurrentUserDep,
    supabase: SupabaseDep,
) -> SavedItinerary:
    """Save a full ``ItineraryResponse`` under a title."""
    request = SaveItineraryRequest(
        title=body.title,
        destination=body.itinerary.city_name,
        city_id=body.city_id,
        days_data=body.itinerary.daily_plans,
        total_cost_usd=body.itinerary.total_cost_usd,
        agent_reasoning=body.itinerary.agent_reasoning,
    )
    return await save_itinerary(request, user, supabase)


@router.get("", response_model=SavedItineraryList)
async def list_itineraries(
    user: CurrentUserDep,
    supabase: SupabaseDep,
) -> SavedItineraryList:
    """Return the caller's saved itinerary history (newest first)."""
    try:
        result = (
            supabase.table("user_itineraries")
            .select("*")
            .eq("user_id", user.id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list itineraries: {exc}",
        ) from exc
    items = [_row_to_saved(r) for r in rows]
    return SavedItineraryList(items=items, count=len(items))


@router.get("/{itinerary_id}", response_model=SavedItinerary)
async def get_itinerary(
    itinerary_id: UUID,
    user: CurrentUserDep,
    supabase: SupabaseDep,
) -> SavedItinerary:
    try:
        result = (
            supabase.table("user_itineraries")
            .select("*")
            .eq("id", str(itinerary_id))
            .eq("user_id", user.id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load itinerary: {exc}",
        ) from exc
    if not rows:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return _row_to_saved(rows[0])
