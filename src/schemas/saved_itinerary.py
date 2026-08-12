"""Saved itinerary schemas (Phase 5.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.itinerary import DailyItinerary, ItineraryResponse


class SaveItineraryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    city_id: UUID | None = None
    days_data: list[DailyItinerary] | dict[str, Any] = Field(
        ...,
        description="Daily plans JSON (list of DailyItinerary or full ItineraryResponse-like object).",
    )
    total_cost_usd: float | None = Field(default=None, ge=0)
    agent_reasoning: str | None = None


class SavedItinerary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    title: str
    destination: str
    city_id: UUID | None = None
    days_data: Any
    total_cost_usd: float | None = None
    agent_reasoning: str | None = None
    created_at: datetime


class SavedItineraryList(BaseModel):
    items: list[SavedItinerary]
    count: int


class SaveFromGenerateRequest(BaseModel):
    """Convenience: persist a freshly generated ``ItineraryResponse``."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=200)
    itinerary: ItineraryResponse
    city_id: UUID | None = None
