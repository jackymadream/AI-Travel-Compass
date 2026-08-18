"""Place / Maps URL geocoding for Custom Spot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.services.geocode_service import resolve_place

router = APIRouter(prefix="/geocode", tags=["geocode"])


class GeocodeRequest(BaseModel):
    query: str | None = Field(default=None, max_length=2000)
    name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)


@router.post("")
def geocode_place(body: GeocodeRequest) -> dict[str, Any]:
    hit = resolve_place(query=body.query, name=body.name, city=body.city)
    if not hit:
        return {"ok": False, "error": "PLACE_NOT_FOUND"}
    return {
        "ok": True,
        "lat": hit["lat"],
        "lon": hit["lon"],
        "label": hit.get("label"),
        "source": hit.get("source"),
    }
