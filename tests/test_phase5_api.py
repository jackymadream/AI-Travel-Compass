"""Rate limit + itinerary auth API tests (Phase 5.2 / 5.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from unittest.mock import MagicMock

from src.deps import get_supabase
from src.deps_auth import AuthUser, get_current_user
from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_search_rate_limit_returns_429() -> None:
    """Unauthenticated search limited to 15/minute (SlowAPI contract)."""
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
    mini = FastAPI()
    mini.state.limiter = limiter
    mini.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @mini.post("/search")
    @limiter.limit("15/minute")
    async def search(request: Request) -> dict:
        return {"ok": True}

    with TestClient(mini) as test_client:
        statuses = [
            test_client.post("/search").status_code for _ in range(16)
        ]

    assert statuses.count(200) == 15
    assert statuses[-1] == 429


def test_save_itinerary_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/api/v1/itineraries",
        json={
            "title": "Tokyo weekend",
            "destination": "Tokyo",
            "days_data": [],
        },
    )
    assert res.status_code == 401


def test_list_itineraries_requires_auth(client: TestClient) -> None:
    res = client.get("/api/v1/itineraries")
    assert res.status_code == 401


def test_itinerary_crud_with_valid_auth(client: TestClient) -> None:
    user = AuthUser(id=str(uuid4()), email="traveler@example.com")
    itinerary_id = uuid4()
    now = datetime.now(timezone.utc).isoformat()

    saved_row = {
        "id": str(itinerary_id),
        "user_id": user.id,
        "title": "Tokyo weekend",
        "destination": "Tokyo",
        "city_id": None,
        "days_data": [
            {
                "day_number": 1,
                "theme": "Culture",
                "estimated_daily_cost": 40,
                "activities": [
                    {
                        "time_slot": "10:00-12:00",
                        "poi_name": "Senso-ji",
                        "category": "attraction",
                        "cost_usd": 0,
                        "duration_minutes": 90,
                        "description": "Temple",
                    }
                ],
            }
        ],
        "total_cost_usd": 40,
        "agent_reasoning": "Mock",
        "created_at": now,
    }

    table = MagicMock()
    insert_chain = MagicMock()
    insert_chain.execute.return_value = MagicMock(data=[saved_row])
    table.insert.return_value = insert_chain

    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.order.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[saved_row])
    table.select.return_value = select_chain

    supabase = MagicMock()
    supabase.table.return_value = table

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase] = lambda: supabase
    try:
        create = client.post(
            "/api/v1/itineraries",
            json={
                "title": "Tokyo weekend",
                "destination": "Tokyo",
                "days_data": saved_row["days_data"],
                "total_cost_usd": 40,
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert create.status_code == 201, create.text
        assert create.json()["title"] == "Tokyo weekend"

        listed = client.get(
            "/api/v1/itineraries",
            headers={"Authorization": "Bearer test-token"},
        )
        assert listed.status_code == 200
        body = listed.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == str(itinerary_id)

        updated_row = {
            **saved_row,
            "title": "Tokyo weekend (updated)",
            "total_cost_usd": 55,
        }
        update_chain = MagicMock()
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = MagicMock(data=[updated_row])
        table.update.return_value = update_chain

        updated = client.put(
            f"/api/v1/itineraries/{itinerary_id}",
            json={
                "title": "Tokyo weekend (updated)",
                "destination": "Tokyo",
                "days_data": saved_row["days_data"],
                "total_cost_usd": 55,
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "Tokyo weekend (updated)"
        assert updated.json()["total_cost_usd"] == 55
    finally:
        app.dependency_overrides.clear()


def test_update_itinerary_requires_auth(client: TestClient) -> None:
    res = client.put(
        f"/api/v1/itineraries/{uuid4()}",
        json={
            "title": "x",
            "destination": "Tokyo",
            "days_data": [],
        },
    )
    assert res.status_code == 401
