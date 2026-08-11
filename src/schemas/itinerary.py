"""Pydantic v2 contracts for the Phase 3 itinerary agent."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.country import Locale


class ActivityCategory(str, Enum):
    ATTRACTION = "attraction"
    FOOD = "food"
    REST = "rest"


class TripPace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class Activity(BaseModel):
    """Single timed stop within a day."""

    model_config = ConfigDict(extra="forbid")

    time_slot: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Human-readable slot, e.g. '09:00-11:00' or 'morning'.",
    )
    poi_name: str = Field(..., min_length=1, max_length=200)
    category: ActivityCategory
    cost_usd: float = Field(..., ge=0, description="Estimated activity cost in USD.")
    duration_minutes: int = Field(..., ge=1, le=24 * 60)
    description: str = Field(..., min_length=1, max_length=2000)


class DailyItinerary(BaseModel):
    """One day of the trip plan."""

    model_config = ConfigDict(extra="forbid")

    day_number: int = Field(..., ge=1, le=7)
    theme: str = Field(..., min_length=1, max_length=200)
    estimated_daily_cost: float = Field(..., ge=0)
    activities: list[Activity] = Field(default_factory=list)


class ItineraryRequest(BaseModel):
    """
    Input to the tool-calling itinerary agent.

    Hard bounds (days 1–7, pace enum, daily budget) are enforced here;
    schedule density and grounding are re-checked by the Schedule Evaluator tool
    (see docs/AGENT_ARCHITECTURE.md).
    """

    model_config = ConfigDict(extra="forbid")

    city_id: UUID = Field(..., description="Target city UUID (Postgres cities.id).")
    days: int = Field(..., ge=1, le=7, description="Trip length in days.")
    pace: TripPace = Field(
        default=TripPace.MODERATE,
        description="Activity density: relaxed / moderate / packed.",
    )
    daily_budget_usd: float = Field(
        ...,
        gt=0,
        description="Per-day spend ceiling used by the Schedule Evaluator.",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Soft interests biasing POI retrieval (e.g. food, museum).",
    )
    locale: Locale = Field(
        default=Locale.EN,
        description="Narrative + POI description locale (en, zh-HK, ja).",
    )


class ItineraryResponse(BaseModel):
    """Validated structured itinerary emitted after Schedule Evaluator pass."""

    model_config = ConfigDict(extra="ignore")

    city_name: str = Field(..., min_length=1)
    total_cost_usd: float = Field(..., ge=0)
    daily_plans: list[DailyItinerary] = Field(default_factory=list)
    agent_reasoning: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Short explanation of pacing and preference trade-offs.",
    )
