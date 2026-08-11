"""Health endpoint tests (liveness + dependency readiness)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _ok_check(**extra: Any) -> dict[str, Any]:
    return {"status": "ok", "detail": "ok", **extra}


def _bad_check(detail: str = "down") -> dict[str, Any]:
    return {"status": "unavailable", "detail": detail}


@pytest.fixture
def client_ok() -> TestClient:
    from src.main import app
    from src.routers.health import get_health_report

    def report() -> dict[str, Any]:
        return {
            "status": "ok",
            "checks": {
                "redis": _ok_check(backend="memory"),
                "vector_db": _ok_check(),
                "database": _ok_check(),
            },
        }

    app.dependency_overrides[get_health_report] = report
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_degraded() -> TestClient:
    from src.main import app
    from src.routers.health import get_health_report

    def report() -> dict[str, Any]:
        return {
            "status": "degraded",
            "checks": {
                "redis": _ok_check(backend="memory"),
                "vector_db": _bad_check("qdrant timeout"),
                "database": _ok_check(),
            },
        }

    app.dependency_overrides[get_health_report] = report
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_liveness_returns_alive(client_ok: TestClient) -> None:
    response = client_ok.get("/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ok_when_all_dependencies_healthy(client_ok: TestClient) -> None:
    response = client_ok.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["vector_db"]["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"


def test_health_degraded_when_vector_db_down(client_degraded: TestClient) -> None:
    response = client_degraded.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["vector_db"]["status"] == "unavailable"
    assert "qdrant" in body["checks"]["vector_db"]["detail"].lower()


def test_build_health_report_aggregates_statuses() -> None:
    from src.services.health_service import build_health_report

    report = build_health_report(
        redis_checker=lambda: _ok_check(backend="redis"),
        vector_checker=lambda: _bad_check("offline"),
        database_checker=lambda: _ok_check(),
    )
    assert report["status"] == "degraded"
    assert report["checks"]["redis"]["status"] == "ok"
    assert report["checks"]["vector_db"]["status"] == "unavailable"

    healthy = build_health_report(
        redis_checker=lambda: _ok_check(),
        vector_checker=lambda: _ok_check(),
        database_checker=lambda: _ok_check(),
    )
    assert healthy["status"] == "ok"
