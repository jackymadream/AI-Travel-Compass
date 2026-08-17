"""POI schema for real-world ingestion (Phase 5.1) and agent retrieval."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ActivityCategory = Literal["attraction", "food", "rest"]


class PoiRecord(BaseModel):
    """
    Canonical POI row used by ingest → Supabase / Qdrant / agent tools.

    Matches the Phase 5.1 contract while retaining agent-friendly fields
    (``city_id``, ``tags``, ``cost_usd``, ``duration_minutes``).
    """

    id: str = Field(..., description="Stable UUID for this POI")
    name: str = Field(..., min_length=1, max_length=300)
    city: str = Field(..., min_length=1, description="City display name / slug")
    category: ActivityCategory
    description: str = Field(default="", max_length=2000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    price_level: int | None = Field(
        default=None,
        ge=0,
        le=4,
        description="0=free … 4=very expensive (Places / heuristic)",
    )
    rating: float | None = Field(default=None, ge=0, le=5)
    safety_score: int = Field(default=3, ge=1, le=5)

    # Agent / hybrid-search helpers
    city_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    cost_usd: float | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    user_ratings_total: int | None = Field(default=None, ge=0)
    primary_type: str | None = None
    address: str | None = None
    photo_url: str | None = None
    source: str = "overpass"
    osm_type: str | None = None
    osm_id: int | None = None
    wikidata: str | None = None

    def embedding_text(self) -> str:
        """Structured chunk for Vertex ``RETRIEVAL_DOCUMENT`` embeddings."""
        tag_line = ", ".join(self.tags) if self.tags else "none"
        parts = [
            f"POI: {self.name}",
            f"City: {self.city}",
            f"Category: {self.category}",
            f"Tags: {tag_line}",
            f"Description: {self.description or self.name}",
        ]
        if self.rating is not None:
            parts.append(f"Rating: {self.rating}")
        if self.price_level is not None:
            parts.append(f"Price level: {self.price_level}")
        if self.address:
            parts.append(f"Address: {self.address}")
        if self.primary_type:
            parts.append(f"Primary type: {self.primary_type}")
        return "\n".join(parts)

    def qdrant_payload(self) -> dict:
        """Payload for ``travel_pois`` (city-scoped RAG, not destinations)."""
        return {
            "poi_id": self.id,
            "city_id": self.city_id,
            "city": self.city,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "lat": self.lat,
            "lon": self.lon,
            "price_level": self.price_level,
            "rating": self.rating,
            "safety_score": self.safety_score,
            "tags": self.tags,
            "cost_usd": self.cost_usd,
            "duration_minutes": self.duration_minutes,
            "user_ratings_total": self.user_ratings_total,
            "primary_type": self.primary_type,
            "address": self.address,
            "photo_url": self.photo_url,
            "source": self.source,
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "wikidata": self.wikidata,
            "text": self.embedding_text(),
        }

    def supabase_row(self) -> dict:
        """Row dict for ``pois`` upsert (requires ``city_id``)."""
        if not self.city_id:
            raise ValueError("city_id is required for Supabase upsert")
        return {
            "id": self.id,
            "city_id": self.city_id,
            "name": self.name,
            "category": self.category,
            "description": self.description or self.name,
            "latitude": self.lat,
            "longitude": self.lon,
            "price_level": self.price_level,
            "rating": self.rating,
            "safety_score": self.safety_score,
            "tags": self.tags,
            "cost_usd": self.cost_usd,
            "duration_minutes": self.duration_minutes,
            "osm_id": self.osm_id,
            "osm_type": self.osm_type,
            "source": self.source,
            "places_primary_type": self.primary_type,
            "user_ratings_total": self.user_ratings_total,
            "address": self.address,
            "photo_url": self.photo_url,
            "is_active": True,
        }
