"""Itinerary generation API — POST /api/v1/itineraries/generate."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.schemas.itinerary import ItineraryRequest, ItineraryResponse
from src.services.agent_service import AgentPlanningError, AgentService

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


def get_agent_service() -> AgentService:
    """FastAPI dependency — overridable in tests."""
    return AgentService()


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
